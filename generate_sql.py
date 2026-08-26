import pandas as pd
import datetime

excel_file = r'c:\Users\DELL\Downloads\8-18\src\BlacklistedAgents.xlsx'
sql_file = r'c:\Users\DELL\Downloads\8-18\src\blacklisted_agents_insert.sql'

df = pd.read_excel(excel_file, header=1)
df.columns = df.columns.str.strip()

def escape_sql(val):
    if pd.isna(val) or val is None or str(val).strip() == '' or str(val).lower() == 'nan':
        return 'NULL'
    s = str(val).strip().replace("'", "''").replace("\\", "\\\\")
    return f"'{s}'"

def format_date(val):
    if pd.isna(val) or val is None:
        return 'NULL'
    try:
        if isinstance(val, (pd.Timestamp, datetime.date, datetime.datetime)):
            return f"'{val.strftime('%Y-%m-%d')}'"
        d = pd.to_datetime(str(val))
        return f"'{d.strftime('%Y-%m-%d')}'"
    except Exception:
        return 'NULL'

def format_int(val):
    if pd.isna(val) or val is None:
        return 'NULL'
    try:
        return str(int(val))
    except Exception:
        return 'NULL'

batch_size = 500

with open(sql_file, 'w', encoding='utf-8') as f:
    f.write("-- Blacklisted Agents SQL Dump\n")
    f.write(f"-- Generated from BlacklistedAgents.xlsx\n")
    f.write(f"-- Total Rows in Excel: {len(df)}\n\n")
    f.write("SET FOREIGN_KEY_CHECKS = 0;\n\n")

    chunk = []
    valid_count = 0
    for idx, row in df.iterrows():
        agent_name = escape_sql(row.get('Agent Name'))
        if agent_name == 'NULL':
            continue
        
        sr_no = format_int(row.get('SR.NO'))
        insurer = escape_sql(row.get('Insurer'))
        insurer_type = escape_sql(row.get('Insurer type'))
        pan = escape_sql(row.get('PAN'))
        agency_code = escape_sql(row.get('Agency Code'))
        b_date = format_date(row.get('Blacklisted date'))
        
        row_str = f"({sr_no}, {insurer}, {insurer_type}, {pan}, {agent_name}, {agency_code}, {b_date}, 'IRDAI', NOW(), NOW())"
        chunk.append(row_str)
        valid_count += 1

        if len(chunk) >= batch_size:
            f.write("INSERT INTO `blacklisted_agents` (`sr_no`, `insurer`, `insurer_type`, `pan`, `agent_name`, `agency_code`, `blacklisted_date`, `source`, `imported_at`, `updated_at`) VALUES\n")
            f.write(",\n".join(chunk) + ";\n\n")
            chunk = []

    if chunk:
        f.write("INSERT INTO `blacklisted_agents` (`sr_no`, `insurer`, `insurer_type`, `pan`, `agent_name`, `agency_code`, `blacklisted_date`, `source`, `imported_at`, `updated_at`) VALUES\n")
        f.write(",\n".join(chunk) + ";\n\n")

    f.write("SET FOREIGN_KEY_CHECKS = 1;\n")

print(f"Successfully generated {sql_file} with {valid_count} valid records.")
