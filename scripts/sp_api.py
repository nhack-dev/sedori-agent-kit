#!/usr/bin/env python3
"""Amazon SP-API（自分の出品アカウント専用のアプリ）を呼ぶ小さな道具

  python3 scripts/sp_api.py fees --asin B0XXXXXXX1 --price 4980 --ship 0          # 試し運転：送る中身だけ
  python3 scripts/sp_api.py fees --asin B0XXXXXXX1 --price 4980 --go              # 手数料の見積り
  python3 scripts/sp_api.py offers --asin B0XXXXXXX1 --go                          # 出品の値段（最安の数件）
  python3 scripts/sp_api.py seigen --asin B0XXXXXXX1 --go                          # 出品に許可が要るか
  python3 scripts/sp_api.py nedan --sku MY-SKU-1 --type PRODUCT --price 4780 --go --preview   # 値段の変更（検証だけ）
  python3 scripts/sp_api.py teishi --sku MY-SKU-1 --type PRODUCT --go --preview               # 在庫0で出品を止める（検証だけ）

使う操作（Amazon 公式の API 定義 github.com/amzn/selling-partner-api-models で名前を確かめた）
  fees   … Product Fees API v0  getMyFeesEstimateForASIN  POST /products/fees/v0/items/{Asin}/feesEstimate
  offers … Product Pricing API v0  getItemOffers  GET /products/pricing/v0/items/{Asin}/offers（毎秒0.5回）
  seigen … Listings Restrictions API 2021-08-01  getListingsRestrictions  GET /listings/2021-08-01/restrictions
  nedan / teishi … Listings Items API 2021-08-01  patchListingsItem  PATCH /listings/2021-08-01/items/{sellerId}/{sku}
             --preview を付けると mode=VALIDATION_PREVIEW（検証だけで出品は変わらない）

鍵（.env）… SPAPI_LWA_CLIENT_ID / SPAPI_LWA_CLIENT_SECRET / SPAPI_REFRESH_TOKEN / SPAPI_SELLER_ID
           SPAPI_MARKETPLACE_ID（日本 A1VC38T7YXB528）/ SPAPI_ENDPOINT（日本は Far East の地域）
認証の手順・地域の URL は変わることがあるので、初回は公式ドキュメントで確かめる（playbooks/05-kiyaku.md）。

nedan・teishi は売り場に出る操作です。オーナーが「自動にしてよい」と決めるまで、--preview で検証だけにします。
値段の属性（purchasable_offer）・在庫の属性（fulfillment_availability）の書き方は商品の種類（productType）
ごとの定義に従います。最初の1件は --preview の返事に問題がないことを確かめてから本番にします。
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import json
import sys
import urllib.parse

import kit

LWA = "https://api.amazon.com/auth/o2/token"


def conf():
    return {
        "endpoint": (kit.env("SPAPI_ENDPOINT") or "https://sellingpartnerapi-fe.amazon.com").rstrip("/"),
        "mp": kit.env("SPAPI_MARKETPLACE_ID") or "A1VC38T7YXB528",
    }


def token():
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": kit.env("SPAPI_REFRESH_TOKEN", required=True),
        "client_id": kit.env("SPAPI_LWA_CLIENT_ID", required=True),
        "client_secret": kit.env("SPAPI_LWA_CLIENT_SECRET", required=True),
    }).encode()
    d = kit.http_json(LWA, method="POST", body=body,
                      headers={"Content-Type": "application/x-www-form-urlencoded"})
    if "access_token" not in d:
        sys.exit("止めます：アクセストークンが取れませんでした（鍵を確かめる）")
    return d["access_token"]


def build(a, c):
    """(method, path, query, body) を作る。ここでは送らない。"""
    if a.cmd == "fees":
        body = {"FeesEstimateRequest": {
            "MarketplaceId": c["mp"], "IsAmazonFulfilled": a.fba,
            "PriceToEstimateFees": {
                "ListingPrice": {"CurrencyCode": "JPY", "Amount": a.price},
                "Shipping": {"CurrencyCode": "JPY", "Amount": a.ship}},
            "Identifier": f"kit-{a.asin}"}}
        return "POST", f"/products/fees/v0/items/{a.asin}/feesEstimate", {}, body
    if a.cmd == "offers":
        return "GET", f"/products/pricing/v0/items/{a.asin}/offers", {
            "MarketplaceId": c["mp"], "ItemCondition": "New"}, None
    if a.cmd == "seigen":
        return "GET", "/listings/2021-08-01/restrictions", {
            "asin": a.asin, "sellerId": kit.env("SPAPI_SELLER_ID") or "（SPAPI_SELLER_ID）",
            "marketplaceIds": c["mp"], "conditionType": "new_new"}, None
    seller = kit.env("SPAPI_SELLER_ID") or "（SPAPI_SELLER_ID）"
    path = f"/listings/2021-08-01/items/{seller}/{urllib.parse.quote(a.sku, safe='')}"
    q = {"marketplaceIds": c["mp"]}
    if a.preview:
        q["mode"] = "VALIDATION_PREVIEW"
    if a.cmd == "nedan":
        patch = {"op": "replace", "path": "/attributes/purchasable_offer", "value": [{
            "marketplace_id": c["mp"], "currency": "JPY",
            "our_price": [{"schedule": [{"value_with_tax": a.price}]}]}]}
    else:
        patch = {"op": "replace", "path": "/attributes/fulfillment_availability", "value": [{
            "fulfillment_channel_code": "DEFAULT", "quantity": 0}]}
    return "PATCH", path, q, {"productType": a.type, "patches": [patch]}


def main():
    ap = argparse.ArgumentParser(description="SP-API を呼ぶ（既定は試し運転）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fees", "offers", "seigen"):
        p = sub.add_parser(name)
        p.add_argument("--asin", required=True)
        if name == "fees":
            p.add_argument("--price", type=float, required=True, help="売値（円）")
            p.add_argument("--ship", type=float, default=0, help="購入者が払う送料（円）")
            p.add_argument("--fba", action="store_true", help="倉庫に預けて売る場合")
        p.add_argument("--go", action="store_true")
    for name in ("nedan", "teishi"):
        p = sub.add_parser(name)
        p.add_argument("--sku", required=True)
        p.add_argument("--type", required=True, help="productType（出品中の商品の種類・getListingsItem で確かめる）")
        if name == "nedan":
            p.add_argument("--price", type=float, required=True)
        p.add_argument("--preview", action="store_true", help="検証だけ（出品は変わらない）")
        p.add_argument("--go", action="store_true")
    a = ap.parse_args()

    c = conf()
    method, path, q, body = build(a, c)
    url = c["endpoint"] + path + ("?" + urllib.parse.urlencode(q) if q else "")
    if not a.go:
        print("試し運転です（送りません）。送る中身：")
        print(f"  {method} {url}")
        if body is not None:
            print("  " + json.dumps(body, ensure_ascii=False))
        if a.cmd in ("nedan", "teishi") and not a.preview:
            print("  ※ --preview なしで --go を付けると、売り場の出品が本当に変わります")
        return
    if a.cmd in ("nedan", "teishi") and not a.preview:
        print("売り場の出品を変更します。オーナーの許可がある範囲かを確かめてから実行してください。")
    d = kit.http_json(url, method=method, body=body, headers={"x-amz-access-token": token()}, wait=2.0)
    if a.cmd == "fees":
        r = (d.get("payload") or {}).get("FeesEstimateResult") or {}
        fe = (r.get("FeesEstimate") or {}).get("TotalFeesEstimate") or {}
        if r.get("Status") != "Success":
            print("見積りが取れませんでした：", json.dumps(r.get("Error") or d, ensure_ascii=False)[:500])
            sys.exit(1)
        print(f"手数料の見積り 合計 {fe.get('Amount')} {fe.get('CurrencyCode')}")
        for x in (r.get("FeesEstimate") or {}).get("FeeDetailList") or []:
            amt = (x.get("FinalFee") or {}).get("Amount")
            print(f"  {x.get('FeeType')}: {amt}")
        print("→ rieki.py の --fee-en に合計を入れる")
        return
    print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])


if __name__ == "__main__":
    main()
