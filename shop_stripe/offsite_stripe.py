# -*- coding: utf-8 -*-
from django.core.exceptions import ImproperlyConfigured
from django.conf import settings
from django.conf.urls import patterns, url
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.shortcuts import render, redirect
from .forms import CardForm
import stripe
from django.http import Http404
from shop.models_bases import BaseOrder

class StripeBackend(object):
    """
    A django-shop payment backend for the stripe service, this
    is the workhorse view. It processes what the CardForm class
    kicks back to the server.
    """
    backend_name = "Stripe"
    url_namespace = "stripe"

    def __init__(self, shop):
        self.shop = shop
        self.key = getattr(settings, 'SHOP_STRIPE_KEY', None)
        self.currency = getattr(settings, 'SHOP_STRIPE_CURRENCY', None)

    def get_urls(self):
        urlpatterns = patterns(
            '',
            url(r'^(?P<pk>\d+)$', self.stripe_payment_view, name='stripe'),
            url(r'^success/$', self.stripe_return_successful_view,
                name='stripe_success'),
        )
        return urlpatterns

    def stripe_payment_view(self, request, pk=None, template_name="shop_stripe/payment.html",
                            extra_context={}):
        if pk is None:
            raise Http404
        order = self.shop.get_order_for_id(pk)
        if order.user_id <> request.user.id or order.status <> BaseOrder.CONFIRMED:
            raise Http404
        order_id = pk
        extra_context['order_object'] = order
        try:
            stripe.api_key = settings.SHOP_STRIPE_PRIVATE_KEY
            pub_key = settings.SHOP_STRIPE_PUBLISHABLE_KEY
        except AttributeError:
            raise ImproperlyConfigured(
                'You must define the SHOP_STRIPE_PRIVATE_KEY'
                ' and SHOP_STRIPE_PUBLISHABLE_KEY settings'
            )
        error = None
        if request.method == 'POST':
            form = CardForm(request.POST)
            try:
                card_token = request.POST['stripeToken']
            except KeyError:
                return HttpResponseBadRequest('stripeToken not set')
            currency = getattr(settings, 'SHOP_STRIPE_CURRENCY', 'usd')
            amount = self.shop.get_order_total(order)
            amount = str(int(amount * 100))
            if request.user.is_authenticated():
                description = request.user.email
            else:
                description = 'guest customer'
            stripe_dict = {
                'amount': amount,
                'currency': currency,
                'card': card_token,
                'description': description,
            }
            try:
                stripe_result = stripe.Charge.create(**stripe_dict)
            except stripe.CardError as e:
                error = e
            else:
                self.shop.confirm_payment(
                    self.shop.get_order_for_id(order_id),
                    amount,
                    stripe_result['id'],
                    self.backend_name
                )
                return redirect(self.shop.get_finished_url())
        else:
            form = CardForm()
        return render(request, template_name, dict({
            'form': form,
            'error': error,
            'STRIPE_PUBLISHABLE_KEY': pub_key,
            }, **extra_context))

    def stripe_return_successful_view(self, request):
        return HttpResponseRedirect(self.shop.get_finished_url())
