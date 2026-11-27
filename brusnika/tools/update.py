"""Обновление квартир Брусники для сайта «Брусника для агентов».

Запуск из корня репозитория: python3 brusnika/tools/update.py
Выгружает квартиры в продаже и в брони с moskva.brusnika.ru, убирает снятые
с продажи, помечает бронь (bk:1), докачивает планировки новых квартир
в brusnika/plans/ и пересобирает brusnika/flats.json.
Если API не ответил или по какому-то ЖК пришёл пустой список, файлы не меняются.
"""
import datetime
import io
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
API = 'https://moskva.brusnika.ru/api'
PROJ = {'izdanie': 83, 'mons': 82, 'gertzena': 92, 'perviy': 11, 'metronom': 79,
        'rublevskie-dvory': 109, 'belata': 99, 'dom-a': 87}
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'


def get(url, binary=False):
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': '*/*' if binary else 'application/json'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
                return data if binary else json.loads(data.decode('utf-8'))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f'Не удалось получить {url}: {last}')


def fetch_flats(cid, booked):
    res, off = [], 0
    while True:
        d = get(f'{API}/filter/flats/?offset={off}&limit=50&ordering=price_order&is_group=0'
                f'&is_booked={"true" if booked else "false"}&complex={cid}')
        res += d.get('results', [])
        off += 50
        if not d.get('next'):
            return res
        time.sleep(0.6)


def conv(f, bk):
    base = f['price'] or 0
    site = float(f.get('price_marketing') or 0)
    if not (f.get('show_price_marketing') and site and site < base):
        site = base
    promo = f.get('active_promo_price') if f.get('active_promo_price') and f['active_promo_price'] < site else None
    src = f.get('main_flat_image') or ''
    img = (src.rsplit('/', 1)[1].rsplit('.', 1)[0] + '.webp') if src else None
    d = dict(id=f['flat_id'], c=f['complex'], b=f['building_name'], s=f['section_number'], fl=f['floor'],
             ff=f['section_floors_count'], r=f['rooms'], a=f['square'], base=round(base), site=round(site),
             promo=round(promo) if promo else None, pt=f['active_promo_type'] if promo else None,
             pd=(f['active_promo_date'] or '')[:10] if promo else None,
             d=(f.get('delivery_title') or '').replace('Срок сдачи: ', ''), tags=f.get('tags') or [], img=img)
    if bk:
        d['bk'] = 1
    return d, src


def to_webp(raw, is_svg, out):
    from PIL import Image
    if is_svg:
        import cairosvg
        png = cairosvg.svg2png(bytestring=raw, output_width=780)
        im = Image.open(io.BytesIO(png)).convert('RGBA')
    else:
        im = Image.open(io.BytesIO(raw)).convert('RGBA')
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    im = bg.convert('RGB')
    im.thumbnail((800, 600))
    canvas = Image.new('RGB', (800, 600), (255, 255, 255))
    canvas.paste(im, ((800 - im.width) // 2, (600 - im.height) // 2))
    canvas.save(out, 'WEBP', quality=72)


def main():
    flats_path = os.path.join(ROOT, 'flats.json')
    plans_dir = os.path.join(ROOT, 'plans')
    old = json.load(open(flats_path, encoding='utf-8'))
    old = old['flats'] if isinstance(old, dict) else old
    old_ids = {f['id'] for f in old}
    flats, report, new_plans = [], [], 0
    for slug, cid in PROJ.items():
        sale = fetch_flats(cid, False)
        bkd = fetch_flats(cid, True)
        if not sale:
            print(f'Пустой список квартир в продаже по ЖК {slug} — обновление остановлено')
            sys.exit(1)
        sale_ids = {x['flat_id'] for x in sale}
        items = [conv(f, False) for f in sale] + [conv(f, True) for f in bkd if f['flat_id'] not in sale_ids]
        for d, src in items:
            if d['img'] and src and not os.path.exists(os.path.join(plans_dir, d['img'])):
                try:
                    to_webp(get(src, binary=True), src.lower().endswith('.svg'), os.path.join(plans_dir, d['img']))
                    new_plans += 1
                except Exception as e:  # noqa: BLE001
                    print('Планировка не сохранена', d['img'], e)
                    d['img'] = None
                time.sleep(0.3)
        ids = {d['id'] for d, _ in items}
        gone = len({f['id'] for f in old if f['c'] == cid} - ids)
        new = len(ids - old_ids)
        flats += [d for d, _ in items]
        report.append(f'{slug}: в продаже {len(sale)}, в брони {sum(1 for d, _ in items if d.get("bk"))}, '
                      f'снято {gone}, новых {new}')
        time.sleep(0.5)
    msk = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=3)
    json.dump({'date': msk.strftime('%d.%m.%Y'), 'updated': msk.strftime('%d.%m.%Y %H:%M'), 'flats': flats},
              open(flats_path, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    print('\n'.join(report))
    print('Всего квартир:', len(flats), '· новых планировок:', new_plans)


if __name__ == '__main__':
    main()
