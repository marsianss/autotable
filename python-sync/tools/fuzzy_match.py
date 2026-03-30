"""Removed: fuzzy_match

Fuzzy matching against WooCommerce caches is disabled. This repository is
kept focused on UNAS fetch + translation only. The original implementation
was archived to `backup_unas_keep/` before cleanup.
"""

print('fuzzy_match removed — WooCommerce integration not included')
raise SystemExit(0)
            r['BestMatch_Score'] = best['combined']
            r['BestMatch_Method'] = 'fuzzy'
        else:
            r['BestMatch_SKU'] = best['wp_sku'] if best else ''
            r['BestMatch_WP_Id'] = str(best['wp_id'] or '') if best else ''
            r['BestMatch_Score'] = best['combined'] if best else ''
            r['BestMatch_Method'] = 'candidate' if best else ''

        updated_rows.append(r)
        if i % 25 == 0 or i == len(rows):
            elapsed = time.time() - start
            print(f'  {i}/{len(rows)} rows processed (elapsed {elapsed:.1f}s)')

    # write report and updated CSV
    print('Writing report to', REPORT_PATH)
    with open(REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # write CSV (preserve existing columns plus added ones)
    keys = list(rows[0].keys()) if rows else ['Id','Sku','Name']
    for extra in ['BestMatch_SKU','BestMatch_WP_Id','BestMatch_Score','BestMatch_Method']:
        if extra not in keys:
            keys.append(extra)

    print('Writing updated CSV to', CSV_PATH)
    with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        for r in updated_rows:
            writer.writerow(r)

    print('Done. Report entries:', len(report))

if __name__ == '__main__':
    main()
