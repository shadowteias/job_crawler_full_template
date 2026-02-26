# api/management/commands/import_companies_from_csv.py

import csv
import json
from datetime import datetime
from django.core.management.base import BaseCommand
from api.models import Company


class Command(BaseCommand):
    help = 'Import companies from CSV file'

    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, help='Path to CSV file')
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing companies',
        )

    def handle(self, *args, **options):
        csv_file = options['csv_file']
        update_existing = options.get('update', False)

        self.stdout.write(f'Importing from {csv_file}...')

        created = 0
        updated = 0
        skipped = 0

        with open(csv_file, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            fields = reader.fieldnames

            for row in reader:
                name = row.get('name', '').strip()
                if not name:
                    skipped += 1
                    continue

                # 기존 회사 조회
                existing = None
                if update_existing:
                    # ID로 조회
                    if row.get('id'):
                        existing = Company.objects.filter(id=row['id']).first()
                    # 없으면 이름으로 조회
                    if not existing:
                        existing = Company.objects.filter(name=name).first()

                # 필드 매핑
                data = {}
                for field in [
                    'homepage_url',
                    'homepage_url_status',
                    'homepage_last_status_code',
                    'homepage_checked_at',
                    'ceo_name',
                    'bizr_no',
                    'stock_code',
                    'dart_corp_code',
                    'dart_modify_date',
                    'est_dt',
                    'acc_mt',
                    'swdb_fin_year',
                    'recruits_url',
                    'recruits_url_status',
                    'industry',
                    'address',
                    'region',
                ]:
                    val = row.get(field, '').strip()
                    if val:
                        # 날짜 필드 변환
                        if field in ['homepage_checked_at', 'created_at', 'updated_at']:
                            if val:
                                try:
                                    val = datetime.fromisoformat(val.replace('Z', '+00:00'))
                                except:
                                    val = None
                        elif field == 'est_dt':
                            if val:
                                try:
                                    val = datetime.strptime(val, '%Y-%m-%d').date()
                                except:
                                    try:
                                        val = datetime.strptime(val, '%Y%m%d').date()
                                    except:
                                        val = None
                        elif field in ['homepage_last_status_code', 'swdb_fin_year']:
                            try:
                                val = int(val) if val else None
                            except:
                                val = None
                        
                        if val:
                            data[field] = val

                # source_meta (JSON)
                source_meta = row.get('source_meta', '').strip()
                if source_meta:
                    try:
                        data['source_meta'] = json.loads(source_meta)
                    except:
                        data['source_meta'] = {}

                if existing and update_existing:
                    # 업데이트
                    for key, val in data.items():
                        setattr(existing, key, val)
                    existing.save()
                    updated += 1
                elif existing:
                    # 기존 있음 - 스킵
                    skipped += 1
                else:
                    # 신규 생성
                    data['name'] = name
                    # name_norm 생성
                    data['name_norm'] = name.lower().replace('주식회사', '').replace('(주)', '').replace('有限公司', '').strip()
                    
                    # homepage_host 생성
                    if data.get('homepage_url'):
                        from urllib.parse import urlparse
                        try:
                            url = data['homepage_url']
                            if not url.startswith(('http://', 'https://')):
                                url = 'https://' + url
                            host = urlparse(url).netloc
                            if host.startswith('www.'):
                                host = host[4:]
                            data['homepage_host'] = host
                        except:
                            pass

                    Company.objects.create(**data)
                    created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Import complete: created={created}, updated={updated}, skipped={skipped}'
            )
        )
