#!/usr/bin/env python3
"""仕入れ候補を「通す／止める／要確認」に分ける（ネットにつながない）

  python3 scripts/hantei.py samples/candidates.csv
  python3 scripts/hantei.py samples/candidates.csv --json > out/hantei.json

入力は CSV（列の意味は samples/candidates.csv の1行目と playbooks/01-sagasu.md）。
値は Keepa・SP-API・売り場の画面などから集めて入れる。空欄は「分からない」。
  分からない ≠ 安全。空欄が判定に要る項目なら「要確認」にして、通さない。

止める条件（1つでも当たれば止める）と初期値は config/settings.json の hantei。
利益の判定は rieki.py と同じ式（sell と cost があるときだけ）。
"""

import os as _ng_os, sys as _ng_sys  # N-Hack 専用の門（下の3行を消すとこのキットは動きません）
_ng_sys.path.insert(0, _ng_os.path.dirname(_ng_os.path.abspath(__file__)))
import nhack_gate as _nhack_gate  # noqa: E402,F401

import argparse
import csv
import json
import sys

import kit
import rieki

NUM = ["rank", "uriage_tsuki", "shuppinsha", "shuppinsha_30d_mae", "hontai_cart_90", "hontai_cart_365",
       "jibun_hassou_cart", "ima", "avg30", "avg90", "avg180", "kakaku_kotei_hi", "hyouka", "sell", "cost", "fee_en"]


def num(v):
    if v is None:
        return None
    v = str(v).strip().replace(",", "")
    if v == "" or v.lower() in ("none", "null", "-", "不明"):
        return None
    return float(v)


def hantei(row, s):
    h = s["hantei"]
    d = {k: num(row.get(k)) for k in NUM}
    tomeru, kakunin, yoi = [], [], []

    def need(key, label):
        if d[key] is None:
            kakunin.append(f"{label}が分からない")
            return False
        return True

    kat = (row.get("category") or "").strip()
    for w in h["kinshi_kategori"]:
        if w and w in kat:
            tomeru.append(f"カテゴリ「{kat}」は初期設定で外す（許可・法律の確認が要る）")
            break
    kyoka = (row.get("kyoka") or "").strip().lower()
    if kyoka in ("yes", "要", "true", "1"):
        tomeru.append("出品に許可が要る（SP-API の出品制限で確認済み）")
    elif kyoka in ("", "unknown", "不明"):
        kakunin.append("出品制限をまだ確かめていない（getListingsRestrictions）")

    if need("rank", "ランキング") and d["rank"] > h["rank_max"]:
        tomeru.append(f"ランキング {d['rank']:.0f} 位 > {h['rank_max']} 位")
    if need("uriage_tsuki", "月の販売数") and d["uriage_tsuki"] < h["uriage_tsuki_min"]:
        tomeru.append(f"月の販売数 {d['uriage_tsuki']:.0f} < {h['uriage_tsuki_min']}")
    if need("shuppinsha", "出品者の数"):
        if d["shuppinsha"] < h["shuppinsha_min"]:
            tomeru.append(f"出品者 {d['shuppinsha']:.0f} 人（{h['shuppinsha_min']} 人未満はメーカー・独占の恐れ）")
        if d["uriage_tsuki"] and d["shuppinsha"] / d["uriage_tsuki"] > h["shuppinsha_per_uriage_max"]:
            tomeru.append("需要より出品者が多い")
    if d["shuppinsha"] is not None and d["shuppinsha_30d_mae"]:
        gen = 1 - d["shuppinsha"] / d["shuppinsha_30d_mae"]
        if gen >= h["shuppinsha_kyuugen_ritsu"] and not (d["uriage_tsuki"] is not None and d["uriage_tsuki"] < h["uriage_tsuki_min"]):
            tomeru.append(f"30日で出品者が {gen * 100:.0f}% 減った（権利の申し立ての恐れ）")
    for key, label in (("hontai_cart_90", "90日"), ("hontai_cart_365", "365日")):
        if need(key, f"売り場本体のカート割合（{label}）") and d[key] > h["hontai_cart_max"]:
            tomeru.append(f"売り場本体がカートを {d[key] * 100:.0f}% 取っている（{label}）")
    if d["jibun_hassou_cart"] is None:
        kakunin.append("自己発送の出品者がカートを取れているか分からない")
    elif d["jibun_hassou_cart"] < h["jibun_hassou_cart_min"]:
        tomeru.append(f"自己発送のカート取得 {d['jibun_hassou_cart'] * 100:.0f}% < {h['jibun_hassou_cart_min'] * 100:.0f}%")
    if None not in (d["ima"], d["avg90"], d["avg180"]):
        if d["ima"] < d["avg90"] < d["avg180"] and not h["kakaku_sagari_ok"]:
            tomeru.append("値段が下がり続けている（今 < 90日平均 < 180日平均）")
        if d["avg30"] is not None and d["avg30"] > d["avg90"] > d["avg180"]:
            yoi.append("値段が上がり続けている")
    else:
        kakunin.append("値段の履歴（今・90日・180日の平均）が足りない")
    if d["kakaku_kotei_hi"] is not None and d["kakaku_kotei_hi"] >= h["kakaku_kotei_hi"]:
        tomeru.append(f"値段が {d['kakaku_kotei_hi']:.0f} 日動いていない（値段を守るメーカーの合図）")
    if d["hyouka"] is not None and d["hyouka"] < h["hyouka_min"]:
        tomeru.append(f"商品の評価 {d['hyouka']} < {h['hyouka_min']}")

    r = None
    if d["sell"] is not None and d["cost"] is not None:
        r = rieki.keisan(d["sell"], d["cost"], s, d["fee_en"])
        if not r["dashite_yoi"]:
            tomeru.extend(r["riyuu"])
    else:
        kakunin.append("売値か仕入れ値がない（利益を出せない）")

    kekka = "止める" if tomeru else ("要確認" if kakunin else "通す")
    return {"id": row.get("id", ""), "title": row.get("title", ""), "kekka": kekka,
            "tomeru": tomeru, "kakunin": kakunin, "yoi": yoi, "rieki": r}


def main():
    ap = argparse.ArgumentParser(description="仕入れ候補の判定")
    ap.add_argument("csv")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    s = kit.settings()
    with open(a.csv, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("止めます：候補が0件です（ファイルの1行目が列名になっているか確かめる）")
    out = [hantei(r, s) for r in rows]
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    kazu = {"通す": 0, "要確認": 0, "止める": 0}
    for o in out:
        kazu[o["kekka"]] += 1
        print(f"[{o['kekka']}] {o['id']} {o['title']}")
        for t in o["tomeru"]:
            print(f"    止める理由：{t}")
        for t in o["kakunin"]:
            print(f"    確かめること：{t}")
        if o["rieki"]:
            print(f"    利益 {kit.yen(o['rieki']['profit'])} ／ ROI {kit.pct(o['rieki']['roi'])}（手数料は{o['rieki']['fee_src']}）")
    print(f"\n母数 {len(out)} 件 → 通す {kazu['通す']} ／ 要確認 {kazu['要確認']} ／ 止める {kazu['止める']}")


if __name__ == "__main__":
    main()
