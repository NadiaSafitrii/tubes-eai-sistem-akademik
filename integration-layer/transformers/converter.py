import csv
import io
import json
import xml.etree.ElementTree as ET
from datetime import datetime

def csv_to_cdm(csv_string):
    """Mengubah format CSV dari Keuangan menjadi JSON (Canonical Data Model)."""
    reader = csv.DictReader(io.StringIO(csv_string.strip()))
    results = []
    
    for row in reader:
        cdm_message = {
            "student_id": row.get("student_id", ""),
            "event_type": "spp.paid" if row.get("status") == "paid" else "spp.created",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "payload": row
        }
        results.append(cdm_message)
        
    return json.dumps(results)

def xml_to_cdm(xml_string):
    """Mengubah format XML dari Presensi menjadi JSON (Canonical Data Model)."""
    root = ET.fromstring(xml_string)
    
    cdm_message = {
        "student_id": root.findtext("student_id") or "",
        "event_type": "attendance.record",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "payload": {child.tag: child.text for child in root}
    }
    
    return json.dumps(cdm_message)