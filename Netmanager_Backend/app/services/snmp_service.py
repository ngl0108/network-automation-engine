from pysnmp.hlapi import SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity, getCmd
import time

class SnmpManager:
    def __init__(self, target_ip, community='public', version=2, port=161):
        self.target = target_ip
        self.community = community
        self.port = port

        # SnmpEngine은 공유 가능하지만, 간단히 인스턴스마다 생성
        self.snmp_engine = SnmpEngine()
        self.community_data = CommunityData(community, mpModel=1)  # v2c
        self.transport = UdpTransportTarget((target_ip, port), timeout=1.0, retries=1)
        self.context = ContextData()

    def _get_request(self, oids):
        """SNMP GET 요청을 보내고 결과를 반환"""
        try:
            iterator = getCmd(
                self.snmp_engine,
                self.community_data,
                self.transport,
                self.context,
                *[ObjectType(ObjectIdentity(oid)) for oid in oids]
            )

            errorIndication, errorStatus, errorIndex, varBinds = next(iterator)

            if errorIndication:
                # 타임아웃 등 네트워크 에러
                return None
            elif errorStatus:
                print(f"[SNMP Error] {self.target}: {errorStatus.prettyPrint()}")
                return None
            else:
                result = {}
                for varBind in varBinds:
                    oid = str(varBind[0])
                    val = varBind[1]
                    result[oid] = str(val)
                return result
        except Exception as e:
            print(f"[SNMP Exception] {self.target}: {e}")
            return None

    def check_status(self):
        """
        기본 상태 체크 (System Description, Uptime)
        성공하면 Online, 실패하면 Offline
        """
        oids = ['1.3.6.1.2.1.1.1.0', '1.3.6.1.2.1.1.3.0']  # sysDescr, sysUpTime
        data = self._get_request(oids)

        if data:
            return {
                "status": "online",
                "uptime": data.get('1.3.6.1.2.1.1.3.0', 'Unknown'),
                "description": data.get('1.3.6.1.2.1.1.1.0', 'Unknown')
            }
        else:
            return {"status": "offline"}

    def get_resource_usage(self):
        """
        CPU, Memory 사용량 조회 (Cisco 기준 OID)
        """
        oids = [
            '1.3.6.1.4.1.9.9.109.1.1.1.1.5.1',  # CPU 5min
            '1.3.6.1.4.1.9.9.48.1.1.1.5.1',   # Mem Used
            '1.3.6.1.4.1.9.9.48.1.1.1.6.1'    # Mem Free
        ]

        data = self._get_request(oids)

        if not data:
            return None

        cpu = data.get('1.3.6.1.4.1.9.9.109.1.1.1.1.5.1', '0')
        mem_used = int(data.get('1.3.6.1.4.1.9.9.48.1.1.1.5.1', 0))
        mem_free = int(data.get('1.3.6.1.4.1.9.9.48.1.1.1.6.1', 0))

        total_mem = mem_used + mem_free
        mem_percent = (mem_used / total_mem * 100) if total_mem > 0 else 0

        return {
            "cpu_usage": int(cpu),
            "memory_usage": round(mem_percent, 2)
        }