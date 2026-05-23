from __future__ import annotations
"""Order management tool – create, read, update orders."""

import json
from datetime import datetime, timedelta
from pathlib import Path

_orders = {}
_catalog_ref = None


def _load_orders():
    global _orders
    data_path = Path(__file__).parent / "mock_data" / "orders.json"
    with open(data_path, "r") as f:
        _orders = json.load(f)


_load_orders()


def _get_catalog():
    global _catalog_ref
    if _catalog_ref is None:
        from tools.catalog import _catalog
        _catalog_ref = _catalog
    return _catalog_ref


def get_order(order_id: str) -> dict | None:
    order_id = order_id.upper().strip()
    order = _orders.get(order_id)
    if order:
        return {**order, "order_id": order_id}
    return None


def create_order(
    customer_name: str,
    product_id: str,
    size: str,
    quantity: int = 1,
    payment_method: str = "COD",
    address: str = "",
) -> dict:
    payment_method = payment_method or "COD"
    catalog = _get_catalog()
    product = catalog.get(product_id)
    if not product:
        return {"error": f"Product {product_id} not found"}

    # Auto-select size when product has exactly one size option (e.g. FREE SIZE sarees)
    if not size:
        available = [s for s, qty in product["sizes"].items() if qty > 0]
        if len(available) == 1:
            size = available[0]

    from tools.catalog import check_availability
    availability = check_availability(product_id, size)
    if not availability.get("available"):
        return {
            "error": f"Size {size} is out of stock for {product['name']}",
            "available_sizes": availability.get("other_sizes_available", {}),
        }

    amount = product["price"] * quantity
    if payment_method.upper() == "COD":
        if amount >= 5000:
            return {
                "error": f"COD is not available for orders ₹5000 or above. Order total: ₹{amount}. Please choose UPI or Card."
            }
        if product.get("is_custom_stitched"):
            return {"error": "COD is not available for custom-stitched items. Please choose UPI or Card."}

    order_id = f"ORD-{1000 + len(_orders) + 1}"

    base_days = 5 if not product.get("is_custom_stitched") else 12
    est_start = datetime.now() + timedelta(days=base_days)
    est_end = est_start + timedelta(days=2)

    shipping = 0 if amount >= 1499 else 99
    cod_fee = 49 if payment_method.upper() == "COD" else 0
    total = amount + shipping + cod_fee

    payment_link = None
    status = "confirmed"
    if payment_method.upper() != "COD":
        payment_link = f"https://pay.taaraboutique.com/{order_id}?amount={total}"
        status = "pending_payment"

    order = {
        "customer_name": customer_name,
        "product_id": product_id,
        "product_name": product["name"],
        "size": size.upper(),
        "quantity": quantity,
        "amount": amount,
        "shipping_charge": shipping,
        "cod_fee": cod_fee,
        "total": total,
        "payment_method": payment_method.upper(),
        "status": status,
        "created_at": datetime.now().isoformat(),
        "shipped_at": None,
        "delivered_at": None,
        "tracking_url": None,
        "address": address,
        "payment_link": payment_link,
    }

    _orders[order_id] = order
    catalog[product_id]["sizes"][size.upper()] -= quantity

    return {
        "order_id": order_id,
        "status": status,
        "total": total,
        "amount": amount,
        "shipping_charge": shipping,
        "cod_fee": cod_fee,
        "payment_link": payment_link,
        "estimated_delivery": f"{est_start.strftime('%b %d')} - {est_end.strftime('%b %d, %Y')}",
        "product_name": product["name"],
        "size": size.upper(),
    }


def update_order(order_id: str, updates: dict) -> dict:
    order = _orders.get(order_id.upper())
    if not order:
        return {"error": f"Order {order_id} not found"}

    VALID_TRANSITIONS = {
        "pending_payment": ["confirmed", "cancelled"],
        "confirmed": ["shipped", "cancelled"],
        "shipped": ["delivered"],
        "delivered": [],
        "cancelled": [],
    }

    if "status" in updates:
        new_status = updates["status"]
        current_status = order["status"]
        if new_status not in VALID_TRANSITIONS.get(current_status, []):
            return {
                "error": f"Cannot change status from '{current_status}' to '{new_status}'",
                "valid_transitions": VALID_TRANSITIONS.get(current_status, []),
            }

    if "payment_method" in updates:
        new_payment = updates["payment_method"].upper()
        amount = order["amount"]
        shipping = order.get("shipping_charge", 0)
        if new_payment == "COD":
            if amount >= 5000:
                return {"error": f"COD is not available for orders ₹5000 or above (total: ₹{amount})."}
            order["payment_method"] = "COD"
            order["cod_fee"] = 49
            order["total"] = amount + shipping + 49
            order["payment_link"] = None
            order["status"] = "confirmed"
        else:
            order["payment_method"] = new_payment
            order["cod_fee"] = 0
            order["total"] = amount + shipping
            order["payment_link"] = f"https://pay.taaraboutique.com/{order_id.upper()}?amount={order['total']}"
            order["status"] = "pending_payment"

    for key, value in updates.items():
        if key in ["status", "tracking_url"]:
            order[key] = value

    return {**order, "order_id": order_id, "updated": True}
