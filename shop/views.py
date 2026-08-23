from django.shortcuts import render, get_object_or_404
from .models import Category, Product, Order, OrderItem
from django.shortcuts import redirect
from django.views.decorators.http import require_POST
from .cart import Cart
from .forms import CartAddProductForm, OrderCreateForm
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import stripe
from django.conf import settings
from django.urls import reverse


def product_list(request, category_slug=None):
    category = None
    categories = Category.objects.all()
    products = Product.objects.filter(available=True)

    if category_slug:
        category = get_object_or_404(Category, slug=category_slug)
        products = products.filter(category=category)

    return render(request, 'shop/product/list.html', {
        'category': category,
        'categories': categories,
        'products': products
    })


def product_detail(request, id, slug):
    product = get_object_or_404(Product, id=id, slug=slug, available=True)
    return render(request, 'shop/product/detail.html', {
        'product': product
    })


@require_POST
def cart_add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    form = CartAddProductForm(request.POST)
    if form.is_valid():
        cd = form.cleaned_data
        cart.add(
            product=product,
            quantity=cd['quantity'],
            override_quantity=cd['override']
        )
    return redirect('shop:cart_detail')


@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, id=product_id)
    cart.remove(product)
    return redirect('shop:cart_detail')


def cart_detail(request):
    cart = Cart(request)
    return render(request, 'shop/cart/detail.html', {'cart': cart})


def order_create(request):
    cart = Cart(request)
    if len(cart) == 0:
        return redirect('shop:product_list')

    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            for item in cart:
                product = item['product']
                if item['quantity'] > product.stock:
                    messages.error(
                        request,
                        f'Недостаточно товара "{product.name}". В наличии только {product.stock} шт.'
                    )
                    return redirect('shop:cart_detail')
            order = form.save(commit=False)
            if request.user.is_authenticated:
                order.user = request.user
            order.save()

            for item in cart:
                OrderItem.objects.create(
                    order=order,
                    product=item['product'],
                    price=item['price'],
                    quantity=item['quantity']
                )
                product = item['product']
                product.stock -= item['quantity']
                product.save()

            cart.clear()

            stripe.api_key = settings.STRIPE_SECRET_KEY

            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'eur',
                        'product_data': {
                            'name': f'Заказ №{order.id}',
                        },
                        'unit_amount': int(order.get_total_cost() * 100),
                    },
                    'quantity': 1,
                }],
                mode='payment',
                success_url=request.build_absolute_uri(
                    reverse('shop:order_success', args=[order.id])
                ),
                cancel_url=request.build_absolute_uri(
                    reverse('shop:order_create')
                ),
                metadata={
                    'order_id': order.id
                }
            )
            return redirect(session.url, code=303)
    else:
        form = OrderCreateForm()

    return render(request, 'shop/order/create.html', {
        'cart': cart,
        'form': form
    })
    # cart = Cart(request)
    # if len(cart) == 0:
    #     return redirect('shop:product_list')

    # if request.method == 'POST':
    #     form = OrderCreateForm(request.POST)
    #     if form.is_valid():
    #         for item in cart:
    #             product = item['product']
    #             if item['quantity'] > product.stock:
    #                 messages.error(
    #                     request,
    #                     f'Недостаточно товара «{product.name}». В наличии только {product.stock} шт.'
    #                 )
    #                 return redirect('shop:cart_detail')

    #         order = form.save(commit=False)
    #         if request.user.is_authenticated:
    #             order.user = request.user
    #         order.save()

    #         for item in cart:
    #             OrderItem.objects.create(
    #                 order=order,
    #                 product=item['product'],
    #                 price=item['price'],
    #                 quantity=item['quantity']
    #             )
    #             product = item['product']
    #             product.stock -= item['quantity']
    #             product.save()

    #         cart.clear()
    #         return render(request, 'shop/order/created.html', {'order': order})
    # else:
    #     form = OrderCreateForm()

    # return render(request, 'shop/order/create.html', {
    #     'cart': cart,
    #     'form': form
    # })


def register(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('shop:product_list')
    else:
        form = UserCreationForm()
    return render(request, 'shop/registration/register.html', {'form': form})


@login_required
def order_list(request):
    orders = request.user.orders.all()
    return render(request, 'shop/order/list.html', {'orders': orders})


def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order.paid = True
    order.save()
    return render(request, 'shop/order/created.html', {'order': order})