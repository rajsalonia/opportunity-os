"""
AI Outreach Manager - High-Capacity Excel (.xlsx, .xls) and CSV Ingestion Engine.
Handles multi-file batch uploads, heuristic column mapping, RFC syntax validation,
company name normalization, deduplication, and safe transactional database persistence.
"""
import csv
import io
import os
import re
import secrets
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any, Optional

try:
    import openpyxl
except ImportError:
    openpyxl = None

try:
    import xlrd
except ImportError:
    xlrd = None

# RFC 5322 compatible email validation pattern
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

ROLE_BASED_PREFIXES = {
    'info', 'support', 'sales', 'admin', 'contact', 'help',
    'careers', 'jobs', 'hello', 'team', 'marketing', 'press',
    'inquiries', 'office', 'hr', 'billing', 'enquiries'
}

DISPOSABLE_DOMAINS = {
    'mailinator.com', 'tempmail.com', '10minutemail.com', 'guerrillamail.com',
    'throwawaymail.com', 'fake.com', 'example.com', 'test.com', 'trashmail.com'
}

COLUMN_PATTERNS = {
    'company_name': [
        r'^(?:company|company[ _]?name|organization|org|employer|firm|corp|account|business)$',
        r'(?:company|employer|firm)'
    ],
    'name': [
        r'^(?:hr[ _]?name|recruiter[ _]?name|contact[ _]?name|full[ _]?name|name|person|contact|hr|recruiter)$',
        r'(?:hr|recruiter|contact|name)'
    ],
    'email': [
        r'^(?:hr[ _]?email|contact[ _]?email|email[ _]?id|email|work[ _]?email|mail|e-mail)$',
        r'(?:email|mail)'
    ],
    'designation': [
        r'^(?:designation|job[ _]?title|title|role|position|post)$',
        r'(?:designation|title|role|position)'
    ],
    'department': [
        r'^(?:department|dept|team|function|business[ _]?unit)$',
        r'(?:dept|department|team)'
    ],
    'location': [
        r'^(?:location|city|region|address|state|country|place)$',
        r'(?:location|city|address)'
    ],
    'linkedin_url': [
        r'^(?:linkedin[ _]?url|linkedin[ _]?profile|linkedin|profile[ _]?url|social)$',
        r'(?:linkedin)'
    ],
    'company_website': [
        r'^(?:company[ _]?website|website|url|web|domain|site|company[ _]?url)$',
        r'(?:website|domain|web[ _]?page|company[ _]?url)'
    ],
    'phone': [
        r'^(?:phone[ _]?number|phone|mobile|contact[ _]?number|tel|cell|telephone)$',
        r'(?:phone|mobile|tel)'
    ],
    'notes': [
        r'^(?:notes|remarks|comments|misc|details|info|description)$',
        r'(?:notes|remarks|comments)'
    ]
}

COMPANY_SUFFIX_REGEX = re.compile(
    r'(?i)\b(?:private limited|pvt\.? ltd\.?|ltd\.?|limited|inc\.?|incorporated|llc|llp|corp\.?|corporation|technologies|solutions|software|services|co\.?|gmbh)\b'
)


def normalize_company_name(raw_name: str) -> Tuple[str, str]:
    """
    Returns (cleaned_display_name, normalized_clustering_key).
    Example: 'Google India Pvt. Ltd.' -> ('Google India', 'googleindia')
    """
    clean = str(raw_name or '').strip()
    clean = re.sub(r'\s+', ' ', clean)
    clean = COMPANY_SUFFIX_REGEX.sub('', clean).strip(' ,.-')
    clean = clean.strip() or str(raw_name or '').strip()
    cluster_key = re.sub(r'[^a-z0-9]', '', clean.lower())
    return clean, cluster_key


def validate_email(email_str: str) -> Tuple[str, str]:
    """
    Validates email syntax and returns (status, notes).
    Status: 'valid', 'role_based', 'disposable', 'malformed', 'missing'.
    Note: Syntax validation is never proof that a mailbox exists or accepts delivery.
    """
    email = str(email_str or '').strip().lower()
    if not email:
        return 'missing', 'Email address is missing.'
    if not EMAIL_REGEX.match(email):
        return 'malformed', 'Malformed syntax; not a standard RFC 5322 email.'
    
    local_part, _, domain = email.partition('@')
    if domain in DISPOSABLE_DOMAINS:
        return 'disposable', f'Disposable or mock domain (@{domain}); delivery will likely fail.'
    if local_part in ROLE_BASED_PREFIXES:
        return 'role_based', f'Role-based generic address ({local_part}@); not a personal HR contact.'
    
    return 'valid', 'Valid syntax. (Note: deliverability requires server handshake at send-time).'


def detect_columns(headers: List[str]) -> Dict[str, str]:
    """
    Maps standard fields to the best-matching input column header.
    Returns: {standard_field_name: matched_header_string}
    """
    mapping = {}
    used_headers = set()

    for field, patterns in COLUMN_PATTERNS.items():
        # First pass: try exact match
        exact_pat = patterns[0]
        for h in headers:
            h_clean = str(h or '').strip().lower()
            if h not in used_headers and re.match(exact_pat, h_clean):
                mapping[field] = h
                used_headers.add(h)
                break
        
        # Second pass: substring match if not matched
        if field not in mapping and len(patterns) > 1:
            sub_pat = patterns[1]
            for h in headers:
                h_clean = str(h or '').strip().lower()
                if h not in used_headers and re.search(sub_pat, h_clean):
                    mapping[field] = h
                    used_headers.add(h)
                    break

    return mapping


def read_spreadsheet_rows(file_bytes: bytes, filename: str) -> Tuple[List[str], List[Dict[str, Any]]]:
    """
    Reads rows from CSV, XLSX, or XLS byte streams into standard dictionary rows.
    Returns (headers, raw_rows).
    """
    ext = os.path.splitext(filename)[1].lower()
    headers: List[str] = []
    raw_rows: List[Dict[str, Any]] = []

    if ext == '.csv':
        # Detect encoding safely
        text_content = None
        for enc in ('utf-8-sig', 'utf-8', 'latin-1', 'cp1252'):
            try:
                text_content = file_bytes.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text_content is None:
            text_content = file_bytes.decode('utf-8', errors='replace')
        
        # Sniff dialect or default to comma
        sample = text_content[:2048]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=',;\t|')
        except Exception:
            dialect = 'excel'
            
        stream = io.StringIO(text_content)
        reader = csv.reader(stream, dialect)
        row_iter = iter(reader)
        try:
            raw_headers = next(row_iter)
            headers = [str(h).strip() for h in raw_headers if str(h).strip()]
            for r in row_iter:
                if not any(r):
                    continue
                row_dict = {}
                for idx, h in enumerate(headers):
                    val = r[idx].strip() if idx < len(r) else ''
                    row_dict[h] = val
                raw_rows.append(row_dict)
        except StopIteration:
            pass

    elif ext == '.xlsx':
        if openpyxl is None:
            raise RuntimeError("openpyxl library is required to read .xlsx files")
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = wb.active
        rows = sheet.iter_rows(values_only=True)
        try:
            first_row = next(rows, None)
            if first_row:
                headers = [str(cell).strip() for cell in first_row if cell is not None and str(cell).strip()]
                header_count = len(headers)
                for r in rows:
                    if not any(r):
                        continue
                    row_dict = {}
                    for idx in range(min(header_count, len(r))):
                        val = r[idx]
                        row_dict[headers[idx]] = str(val).strip() if val is not None else ''
                    raw_rows.append(row_dict)
        finally:
            wb.close()

    elif ext == '.xls':
        if xlrd is None:
            raise RuntimeError("xlrd library is required to read .xls files")
        wb = xlrd.open_workbook(file_contents=file_bytes)
        sheet = wb.sheet_by_index(0)
        if sheet.nrows > 0:
            raw_headers = sheet.row_values(0)
            headers = [str(cell).strip() for cell in raw_headers if str(cell).strip()]
            for r_idx in range(1, sheet.nrows):
                vals = sheet.row_values(r_idx)
                if not any(vals):
                    continue
                row_dict = {}
                for c_idx in range(min(len(headers), len(vals))):
                    val = vals[c_idx]
                    row_dict[headers[c_idx]] = str(val).strip() if val is not None else ''
                raw_rows.append(row_dict)
    else:
        raise ValueError(f"Unsupported spreadsheet format '{ext}'. Upload .xlsx, .xls, or .csv files.")

    return headers, raw_rows


class OutreachImporter:
    """
    Processes single or multiple spreadsheet files, coordinates column mapping,
    performs email verification and deduplication, and stores records in the database.
    """
    def __init__(self, db, clock_fn=None):
        self.db = db
        self.clock = clock_fn or (lambda: datetime.now(timezone.utc).isoformat())

    def preview_file(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Parses a file and returns detected column mappings with a sample preview
        without writing to database yet.
        """
        headers, raw_rows = read_spreadsheet_rows(file_bytes, filename)
        mapping = detect_columns(headers)
        
        # Prepare sample rows (first 5 rows)
        sample = []
        for r in raw_rows[:5]:
            row_preview = {}
            for std_field, mapped_col in mapping.items():
                row_preview[std_field] = r.get(mapped_col, '')
            sample.append(row_preview)
            
        return {
            'filename': filename,
            'total_rows': len(raw_rows),
            'detected_headers': headers,
            'mapping': mapping,
            'sample_preview': sample
        }

    def import_contacts(
        self,
        file_bytes: bytes,
        filename: str,
        custom_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Ingests a spreadsheet, validates contacts, normalizes company names,
        performs deduplication and merging, and stores in PostgreSQL/SQLite.
        """
        headers, raw_rows = read_spreadsheet_rows(file_bytes, filename)
        mapping = custom_mapping or detect_columns(headers)
        
        batch_id = 'batch_' + secrets.token_hex(12)
        now_time = self.clock()

        total_rows = len(raw_rows)
        valid_rows = 0
        duplicate_rows = 0
        incomplete_rows = 0
        suspicious_rows = 0

        # Pre-load existing emails and clustering keys for fast deduplication
        from sqlalchemy import text
        existing_contacts = {}
        with self.db.begin() as con:
            rows = con.execute(text("SELECT id, normalized_email, company_name, name, linkedin_url FROM outreach_contacts WHERE is_duplicate=0")).fetchall()
            for r in rows:
                c_id, n_email, c_name, p_name, l_url = r[0], r[1], r[2], r[3], r[4]
                if n_email:
                    existing_contacts['email:' + n_email] = c_id
                if c_name and p_name:
                    _, c_cluster = normalize_company_name(c_name)
                    p_cluster = re.sub(r'[^a-z0-9]', '', str(p_name).lower())
                    existing_contacts[f'entity:{c_cluster}:{p_cluster}'] = c_id
                if l_url:
                    l_clean = str(l_url).strip().lower().rstrip('/')
                    if l_clean:
                        existing_contacts['linkedin:' + l_clean] = c_id

        # Company cache to reuse outreach_companies records
        company_id_cache = {}
        with self.db.begin() as con:
            c_rows = con.execute(text("SELECT id, normalized_name FROM outreach_companies")).fetchall()
            for cid, cnorm in c_rows:
                company_id_cache[cnorm] = cid

        contacts_to_insert = []
        companies_to_insert = []
        contacts_to_enrich = []

        for row in raw_rows:
            raw_company = str(row.get(mapping.get('company_name', ''), '')).strip()
            raw_name = str(row.get(mapping.get('name', ''), '')).strip()
            raw_email = str(row.get(mapping.get('email', ''), '')).strip()
            designation = str(row.get(mapping.get('designation', ''), '')).strip()
            department = str(row.get(mapping.get('department', ''), '')).strip()
            location = str(row.get(mapping.get('location', ''), '')).strip()
            website = str(row.get(mapping.get('company_website', ''), '')).strip()
            linkedin = str(row.get(mapping.get('linkedin_url', ''), '')).strip()
            phone = str(row.get(mapping.get('phone', ''), '')).strip()
            notes = str(row.get(mapping.get('notes', ''), '')).strip()

            email_status, email_notes = validate_email(raw_email)
            cleaned_company, comp_cluster = normalize_company_name(raw_company or 'Unknown Company')
            norm_email = raw_email.lower()
            name_cluster = re.sub(r'[^a-z0-9]', '', raw_name.lower())

            # Identify if record is incomplete
            is_incomplete = int(not raw_email or (not raw_name and not raw_company) or email_status == 'missing')
            if is_incomplete:
                incomplete_rows += 1
            if email_status in ('role_based', 'disposable', 'malformed'):
                suspicious_rows += 1

            # Identify if contact is duplicate
            duplicate_parent_id = None
            if norm_email and ('email:' + norm_email) in existing_contacts:
                duplicate_parent_id = existing_contacts['email:' + norm_email]
            elif comp_cluster and name_cluster and f'entity:{comp_cluster}:{name_cluster}' in existing_contacts:
                duplicate_parent_id = existing_contacts[f'entity:{comp_cluster}:{name_cluster}']
            elif linkedin and ('linkedin:' + linkedin.lower().rstrip('/')) in existing_contacts:
                duplicate_parent_id = existing_contacts['linkedin:' + linkedin.lower().rstrip('/')]

            is_duplicate = int(duplicate_parent_id is not None)
            if is_duplicate:
                duplicate_rows += 1
                if duplicate_parent_id:
                    enrich = {}
                    if linkedin: enrich['linkedin_url'] = linkedin
                    if phone: enrich['phone'] = phone
                    if designation: enrich['designation'] = designation
                    if department: enrich['department'] = department
                    if location: enrich['location'] = location
                    if enrich:
                        contacts_to_enrich.append((duplicate_parent_id, enrich))
            elif is_incomplete or email_status in ('role_based', 'disposable', 'malformed', 'missing'):
                pass
            else:
                valid_rows += 1

            contact_id = 'cnt_' + secrets.token_hex(12)

            # Ensure company record exists
            if comp_cluster not in company_id_cache:
                comp_id = 'comp_' + secrets.token_hex(12)
                company_id_cache[comp_cluster] = comp_id
                companies_to_insert.append({
                    'id': comp_id,
                    'name': cleaned_company,
                    'normalized_name': comp_cluster,
                    'domain': website or (norm_email.partition('@')[2] if norm_email else ''),
                    'category': self._classify_company(cleaned_company, department, notes),
                    'location': location,
                    'website': website,
                    'linkedin_url': '',
                    'notes': f'Imported from {filename}',
                    'created_at': now_time,
                    'updated_at': now_time
                })
            comp_id = company_id_cache[comp_cluster]

            # Index this new contact in memory for in-batch deduplication
            if not is_duplicate:
                if norm_email:
                    existing_contacts['email:' + norm_email] = contact_id
                if comp_cluster and name_cluster:
                    existing_contacts[f'entity:{comp_cluster}:{name_cluster}'] = contact_id
                if linkedin:
                    existing_contacts['linkedin:' + linkedin.lower().rstrip('/')] = contact_id

            contacts_to_insert.append({
                'id': contact_id,
                'batch_id': batch_id,
                'company_id': comp_id,
                'company_name': cleaned_company,
                'name': raw_name or 'Hiring Team',
                'email': raw_email,
                'normalized_email': norm_email,
                'designation': designation,
                'department': department,
                'location': location,
                'company_website': website,
                'linkedin_url': linkedin,
                'phone': phone,
                'notes': notes,
                'source_filename': filename,
                'email_status': email_status,
                'email_notes': email_notes,
                'is_duplicate': is_duplicate,
                'merged_into_id': duplicate_parent_id,
                'is_incomplete': is_incomplete,
                'outreach_status': 'not_contacted',
                'last_contacted_at': None,
                'created_at': now_time,
                'updated_at': now_time
            })

        # Batch insert into database using transactions
        from outreach_models import batches, companies, contacts, audit_logs
        import json

        with self.db.begin() as con:
            # 1. Insert Batch record
            con.execute(batches.insert().values(
                id=batch_id,
                filename=filename,
                file_size=len(file_bytes),
                total_rows=total_rows,
                valid_rows=valid_rows,
                duplicate_rows=duplicate_rows,
                incomplete_rows=incomplete_rows,
                column_mapping=json.dumps(mapping),
                status='imported',
                created_at=now_time
            ))

            # 2. Insert new companies
            for c_data in companies_to_insert:
                con.execute(companies.insert().values(**c_data))

            # 3. Insert contacts
            for cnt in contacts_to_insert:
                con.execute(contacts.insert().values(**cnt))

            # 3b. Enrich parent contacts from merged duplicates
            for parent_id, enrich_dict in contacts_to_enrich:
                for col_name, col_val in enrich_dict.items():
                    con.execute(text(f"UPDATE outreach_contacts SET {col_name} = :val, updated_at = :upd WHERE id = :pid AND ({col_name} IS NULL OR {col_name} = '')"), {"val": col_val, "upd": now_time, "pid": parent_id})

            # 4. Audit log
            con.execute(audit_logs.insert().values(
                id='aud_' + secrets.token_hex(12),
                event_type='batch_imported',
                target_id=batch_id,
                actor='owner',
                details=json.dumps({
                    'filename': filename,
                    'total': total_rows,
                    'valid': valid_rows,
                    'duplicates': duplicate_rows,
                    'incomplete': incomplete_rows,
                    'suspicious': suspicious_rows
                }),
                created_at=now_time
            ))

        return {
            'batch_id': batch_id,
            'filename': filename,
            'total_rows': total_rows,
            'valid_rows': valid_rows,
            'duplicate_rows': duplicate_rows,
            'incomplete_rows': incomplete_rows,
            'suspicious_rows': suspicious_rows,
            'mapping_used': mapping
        }

    def _classify_company(self, company_name: str, department: str, notes: str) -> str:
        """
        Classifies company type for personalized outreach:
        'ai_ml', 'backend', 'general_software', or 'unknown'.
        """
        text = f"{company_name} {department} {notes}".lower()
        if re.search(r'\b(?:ai|artificial intelligence|machine learning|ml|deep learning|nlp|computer vision|genai|llm|data science)\b', text):
            return 'ai_ml'
        if re.search(r'\b(?:cloud|backend|apis?|distributed systems|infrastructure|database|microservices|saas|devops)\b', text):
            return 'backend'
        if re.search(r'\b(?:software|technologies|tech|solutions|systems|apps?|web|platform|engineering)\b', text):
            return 'general_software'
        return 'unknown'

    def inspect_spreadsheet(self, filename: str, file_bytes: bytes) -> Tuple[List[str], List[Dict[str, Any]], int]:
        headers, raw_rows = read_spreadsheet_rows(file_bytes, filename)
        return headers, raw_rows[:5], len(raw_rows)

    def detect_column_mapping(self, headers: List[str]) -> Dict[str, str]:
        return detect_columns(headers)

    def import_files(self, file_tuples: List[Tuple[str, bytes, Optional[Dict[str, str]]]]) -> List[Dict[str, Any]]:
        results = []
        for filename, file_bytes, custom_mapping in file_tuples:
            res = self.import_contacts(file_bytes, filename, custom_mapping)
            results.append(res)
        return results

