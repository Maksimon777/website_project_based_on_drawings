import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST, require_safe

from .forms import OrderForm
from .models import Order, OrderFile
from .services import OrderConflict, cancel_by_customer, save_customer_order

logger = logging.getLogger(__name__)
PAGE_SIZE = 20


def visible_orders(user):
    if user.is_active and user.is_staff and user.has_perm("orders.view_order"):
        return Order.objects.all()
    return Order.objects.filter(owner=user)


@never_cache
@login_required
@require_safe
def order_list(request):
    page = Paginator(Order.objects.filter(owner=request.user), PAGE_SIZE).get_page(request.GET.get("page"))
    return render(request, "orders/list.html", {"page": page})


@never_cache
@login_required
@require_safe
def detail(request, pk):
    order = get_object_or_404(visible_orders(request.user), pk=pk)
    return render(request, "orders/detail.html", {
        "order": order, "can_edit": order.owner_id == request.user.pk and order.can_edit,
        "files": order.files.all(), "history": order.history.all(),
    })


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def editor(request, pk=None):
    order = get_object_or_404(Order, pk=pk, owner=request.user) if pk else None
    if order and not order.can_edit:
        return render(request, "orders/locked.html", {"order": order}, status=409)
    form = OrderForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None, instance=order,
    )
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            saved = save_customer_order(actor=request.user, form=form, order_id=pk)
        except OrderConflict as error:
            form.add_error(None, str(error))
            status = 409
        except (DatabaseError, OSError) as error:
            logger.error("Order save failed (%s)", type(error).__name__)
            form.add_error(None, "Не удалось сохранить заказ и файлы. Успех не подтверждён. Проверьте список заказов перед повтором и выберите файлы заново.")
            status = 503
        else:
            messages.success(request, "Заказ отправлен." if pk is None else "Изменения сохранены, заказ отправлен на проверку.")
            return redirect("orders:detail", pk=saved.pk)
    return render(request, "orders/form.html", {"form": form, "order": order}, status=status)


@never_cache
@login_required
@require_POST
def cancel(request, pk):
    try:
        cancel_by_customer(actor=request.user, order_id=pk)
    except OrderConflict as error:
        order = get_object_or_404(Order, pk=pk, owner=request.user)
        return render(request, "orders/locked.html", {"order": order, "reason": str(error)}, status=409)
    messages.success(request, "Заказ отменён.")
    return redirect("orders:detail", pk=pk)


@never_cache
@login_required
@require_safe
def download(request, pk):
    attachment = get_object_or_404(
        OrderFile.objects.filter(order__in=visible_orders(request.user)), pk=pk,
    )
    try:
        stream = attachment.file.open("rb")
    except FileNotFoundError:
        raise Http404("Файл не найден в хранилище.")
    response = FileResponse(stream, as_attachment=True,
                            filename=attachment.original_name,
                            content_type="application/octet-stream")
    response["X-Content-Type-Options"] = "nosniff"
    return response
