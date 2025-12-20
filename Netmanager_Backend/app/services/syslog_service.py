import socket
import re
from app.models.log import EventLog
from app.db.session import SessionLocal
from datetime import datetime

def start_syslog_server(host="0.0.0.0", port=514):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"Syslog 서버 시작: {host}:{port}")

    while True:
        data, addr = sock.recvfrom(4096)  # 버퍼 크기 늘림
        raw_log = data.decode('utf-8', errors='ignore')
        print(f"Received syslog from {addr[0]}: {raw_log}")  # 디버깅 print 추가
        save_log(raw_log, addr[0])

def save_log(raw_log: str, source_ip: str):
    db = SessionLocal()
    try:
        # Cisco 로그 더 정확한 파싱 (타임스탬프 포함)
        # 예: *Dec 20 11:30:09.491: %LINK-3-UPDOWN: Interface GigabitEthernet1/0/3, changed state to down
        match = re.search(r'%([A-Z0-9-]+-\d+-[A-Z0-9]+):\s*(.*)', raw_log)
        event_id = match.group(1) if match else "UNKNOWN"
        message = match.group(2).strip() if match else raw_log.strip()

        # severity 판단 개선
        severity = "INFO"
        if any(keyword in raw_log for keyword in ["EMERG", "ALERT", "CRIT", "ERR", "DOWN", "FAIL"]):
            severity = "CRITICAL"
        elif any(keyword in raw_log for keyword in ["WARNING", "UPDOWN", "NOTICE"]):
            severity = "WARNING"

        print(f"Parsed - Severity: {severity}, Event: {event_id}, Message: {message}")  # 디버깅 print

        log = EventLog(
            severity=severity,
            source=source_ip,
            event_id=event_id,
            message=message
        )
        db.add(log)
        db.commit()
        print("로그 저장 성공!")  # 성공 print
    except Exception as e:
        db.rollback()
        print(f"로그 저장 실패: {e}")
    finally:
        db.close()