import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404

from .models import Order, OrderFile, StatusHistory

logger = logging.getLogger(__name__)
S = Order.Status
TRANSITIONS = {
    S.SUBMITTED: {S.REVIEWING, S.CANCELLED},
    S.REVIEWING: {S.NEEDS_INFO, S.IN_PROGRESS, S.CANCELLED},
    S.NEEDS_INFO: {S.REVIEWING, S.CANCELLED},
    S.IN_PROGRESS: {S.NEEDS_INFO, S.READY, S.CANCELLED},
    S.READY: {S.IN_PROGRESS, S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}
EDITABLE_FIELDS = ("title", "category", "description", "teacher_requirements",
                   "deadline", "output_formats", "other_format")


class OrderConflict(Exception):
    pass


def add_history(order, actor, old_status, note=""):
    StatusHistory.objects.create(
        order=order, changed_by=actor, old_status=old_status,
        new_status=order.status, note=note,
    )


def cleanup_files(saved):
    for storage, name in saved:
        try:
            storage.delete(name)
        except OSError:
            logger.error("Could not clean up an uncommitted upload.")


def save_customer_order(*, actor, form, order_id=None):
    saved = []
    try:
        # Row lock serializes client edits with the administrator taking the order.
        # Storage is not transactional, so failures also remove newly written files.
        with transaction.atomic():
            if order_id is None:
                order = Order(owner=actor)
                old_status = ""
            else:
                order = get_object_or_404(Order.objects.select_for_update(), pk=order_id, owner=actor)
                if not order.can_edit:
                    raise OrderConflict("Заказ уже принят в обработку. Редактирование закрыто.")
                if form.cleaned_data.get("revision") != order.revision:
                    raise OrderConflict("Заказ изменился. Откройте его заново перед редактированием.")
                old_status = order.status
                order.revision += 1
            for field in EDITABLE_FIELDS:
                setattr(order, field, form.cleaned_data[field])
            order.status = S.SUBMITTED
            order.save()
            for upload in form.cleaned_data["files"]:
                attachment = OrderFile(order=order, uploaded_by=actor,
                                       original_name=upload.name, size=upload.size)
                storage = attachment.file.storage
                target = attachment.file.field.generate_filename(attachment, upload.name)
                # Track the chosen path before writing, including partial-write errors.
                saved.append((storage, target))
                stored_name = storage.save(target, upload)
                if stored_name != target:
                    saved.append((storage, stored_name))
                attachment.file.name = stored_name
                attachment.save()
            if old_status != order.status:
                add_history(order, actor, old_status,
                            "Клиент отправил уточнения." if old_status else "Заказ отправлен.")
            return order
    except Exception:
        cleanup_files(saved)
        raise


def validate_transition(order, status, assigned_to, feedback):
    if status != order.status and status not in TRANSITIONS[order.status]:
        raise ValidationError("Такой переход статуса недоступен.")
    if status == S.NEEDS_INFO and not feedback.strip():
        raise ValidationError("Напишите клиенту, какую информацию нужно дополнить.")
    if assigned_to and (not assigned_to.is_staff or not assigned_to.is_active):
        raise ValidationError("Исполнитель должен быть активным сотрудником.")
    if status == S.IN_PROGRESS and assigned_to is None:
        raise ValidationError("Перед началом выполнения назначьте исполнителя.")


def update_by_staff(*, actor, order_id, status, assigned_to, feedback, revision):
    if not actor.is_active or not actor.is_staff or not actor.has_perm("orders.change_order"):
        raise PermissionDenied
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if revision != order.revision:
            raise ValidationError("Заказ изменился. Обновите страницу.")
        validate_transition(order, status, assigned_to, feedback)
        old_status = order.status
        order.status, order.assigned_to, order.feedback = status, assigned_to, feedback
        order.revision += 1
        order.save()
        if old_status != status:
            add_history(order, actor, old_status, feedback if status == S.NEEDS_INFO else "")
        return order


def cancel_by_customer(*, actor, order_id):
    with transaction.atomic():
        order = get_object_or_404(Order.objects.select_for_update(), pk=order_id, owner=actor)
        if not order.can_edit:
            raise OrderConflict("После принятия в обработку отмену нужно согласовать с командой.")
        old_status = order.status
        order.status = S.CANCELLED
        order.revision += 1
        order.save()
        add_history(order, actor, old_status, "Отменён клиентом.")
