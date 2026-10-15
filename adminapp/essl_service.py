from venv import logger
import xml.etree.ElementTree as ET
import requests
from django.conf import settings


SOAP_NAMESPACE = "http://schemas.xmlsoap.org/soap/envelope/"
SERVICE_NAMESPACE = "http://tempuri.org/"


def call_essl(method, parameters):
    """Send a SOAP request to the eSSL web service with debugging."""
    print("DEBUG: sync_essl_attendance VIEW CALLED", flush=True)

    print("DEBUG 0: call_essl started", flush=True)
    print("DEBUG method:", method, flush=True)

    if not all([
        settings.ESSL_SOAP_URL,
        settings.ESSL_USERNAME,
        settings.ESSL_PASSWORD,
    ]):
        raise RuntimeError("eSSL configuration is incomplete.")

    envelope = ET.Element(
        f"{{{SOAP_NAMESPACE}}}Envelope"
    )
    body = ET.SubElement(
        envelope, f"{{{SOAP_NAMESPACE}}}Body"
    )
    operation = ET.SubElement(
        body, f"{{{SERVICE_NAMESPACE}}}{method}"
    )

    for key, value in parameters.items():
        element = ET.SubElement(
            operation, f"{{{SERVICE_NAMESPACE}}}{key}"
        )
        element.text = str(value)

    payload = ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True,
    )

    print("DEBUG 1: Sending request to eSSL", flush=True)

    response = requests.post(
        settings.ESSL_SOAP_URL,
        data=payload,
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{SERVICE_NAMESPACE}{method}"',
        },
        timeout=30,
    )

    print(
        "DEBUG 2: eSSL HTTP status:",
        response.status_code,
        flush=True,
    )
    print(
        "DEBUG 3: Response content type:",
        response.headers.get("Content-Type"),
        flush=True,
    )
    print(
        "DEBUG 4: Raw SOAP response:",
        response.text[:5000],
        flush=True,
    )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    fault = root.find(f".//{{{SOAP_NAMESPACE}}}Fault")
    if fault is not None:
        fault_text = "".join(fault.itertext()).strip()
        print("DEBUG SOAP FAULT:", fault_text, flush=True)
        raise RuntimeError("eSSL SOAP fault: " + fault_text)

    result = root.find(
        f".//{{{SERVICE_NAMESPACE}}}{method}Result"
    )

    if result is None:
        print(
            "DEBUG 5: SOAP result element not found",
            flush=True,
        )
        raise RuntimeError(
            f"Missing {method}Result in eSSL response."
        )

    result_text = (result.text or "").strip()

    print("DEBUG 6: SOAP result text:", repr(result_text), flush=True)

    return result_text


def get_employee_codes():
    """Retrieve employee codes for the configured location."""

    result = call_essl(
        "GetEmployeeCodes",
        {
            "UserName": settings.ESSL_USERNAME,
            "Password": settings.ESSL_PASSWORD,
            "EmployeeLocation": (
                settings.ESSL_EMPLOYEE_LOCATION
            ),
        },
    )

    if not result:
        return []

    return list(dict.fromkeys(
        code.strip()
        for code in result.split(",")
        if code.strip()
    ))


def get_employee_details(employee_code):
    """Retrieve and parse details for one employee."""

    result = call_essl(
        "GetEmployeeDetails",
        {
            "UserName": settings.ESSL_USERNAME,
            "Password": settings.ESSL_PASSWORD,
            "EmployeeCode": employee_code,
        },
    )

    details = {}

    for item in result.split(","):
        key, separator, value = item.partition("=")

        if separator:
            details[key.strip()] = value.strip()

    return {
        "employee_code": str(employee_code),
        "name": details.get("EmployeeName", ""),
        "location": details.get("EmployeeLocation", ""),
        "role": details.get("EmployeeRole", ""),
        "raw_details": details,
    }


def get_all_employee_details():
    """Fetch codes first, then retrieve each employee."""

    employee_codes = get_employee_codes()
    employees = []
    errors = []

    for code in employee_codes:
        try:
            employees.append(
                get_employee_details(code)
            )
        except Exception as exc:
            # Continue if one employee fails.
            errors.append({
                "employee_code": code,
                "error": str(exc),
            })

    return {
        "total_codes": len(employee_codes),
        "successful": len(employees),
        "failed": len(errors),
        "employees": employees,
        "errors": errors,
    }



from django.utils import timezone
from .models import BiometricEmployeeMapping


def sync_essl_employees(tenant=None):
    """
    Fetch employee details from eSSL and create or update
    their biometric mapping records.
    """
    employee_codes = get_employee_codes()[:1659]

    synced = 0
    failed = []

    for code in employee_codes:
        try:
            details = get_employee_details(code)

            BiometricEmployeeMapping.objects.update_or_create(
                tenant=tenant,
                essl_employee_code=str(code),
                defaults={
                    "essl_employee_name": details.get("name", "").strip(),
                    "last_synced_at": timezone.now(),
                    "is_active": True,
                },
            )

            synced += 1

        except Exception as exc:
            failed.append({
                "employee_code": str(code),
                "error": str(exc),
            })

    return {
        "total_codes": len(employee_codes),
        "synced": synced,
        "failed_count": len(failed),
        "failed": failed,
    }