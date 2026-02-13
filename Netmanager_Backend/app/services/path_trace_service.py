from sqlalchemy.orm import Session, selectinload
from sqlalchemy import or_
from typing import List, Dict, Optional, Any, Tuple
import ipaddress
from collections import deque

from app.models.device import Device, Link, Interface

class PathTraceService:
    def __init__(self, db: Session):
        self.db = db
        self._vrf_list_cache: Dict[int, List[str]] = {}
        self._intf_vrf_cache: Dict[Tuple[int, str], Optional[str]] = {}
        self._device_best_intf_cache: Dict[Tuple[int, str], Optional[str]] = {}
        self._l3_interfaces_cache: Optional[List[Interface]] = None
        self._links_by_device_cache: Dict[int, List[Link]] = {}
        self._adjacency_cache: Optional[Dict[int, List[int]]] = None

    def trace_path(self, src_ip: str, dst_ip: str) -> Dict[str, Any]:
        """
        Trace the path from Source IP to Destination IP through the network topology.
        Returns a list of hops and metadata.
        """
        result_meta = {"src_ip": src_ip, "dst_ip": dst_ip}

        # 1. Find Ingress Device (Source Gateway)
        ingress_device, ingress_intf = self._find_device_by_ip(src_ip)
        if not ingress_device:
            return self._add_segments(
                {
                    **result_meta,
                    "error": "Source IP not found in any known network segment.",
                    "path": [],
                }
            )

        # 2. Find Egress Device (Destination Host/Gateway)
        egress_device, egress_intf = self._find_device_by_ip(dst_ip)
        if not egress_device:
            return self._add_segments(
                {
                    **result_meta,
                    "error": "Destination IP not found in any known network segment.",
                    "path": [],
                }
            )

        result_meta = {
            **result_meta,
            "ingress_device_id": ingress_device.id,
            "egress_device_id": egress_device.id,
        }

        # 3. Calculate Path (Prefer L3-aware hop resolution; fallback to BFS)
        if ingress_device.id == egress_device.id:
            # Same device (L3 switch routing between VLANS or same subnet)
            return self._add_segments({
                **result_meta,
                "status": "success",
                "message": "Source and Destination are on the same device.",
                "path": [
                    self._format_node(
                        ingress_device,
                        ingress_intf.name if ingress_intf else "Client",
                        egress_intf.name if egress_intf else "Host",
                    )
                ]
            })

        l3_result = self._trace_path_l3(ingress_device, egress_device, ingress_intf, egress_intf, dst_ip)
        if l3_result:
            l3_result = {**result_meta, **l3_result}
            return self._add_segments(self._try_extend_l2(l3_result, egress_device, dst_ip, egress_intf))

        path_nodes = self._find_shortest_path(ingress_device.id, egress_device.id)
        
        if not path_nodes:
            return self._add_segments({
                **result_meta,
                "status": "partial", 
                "message": "No topological path found between devices.",
                "path": [self._format_node(ingress_device), self._format_node(egress_device)]
            })

        # 4. Format Result
        devs = self.db.query(Device).filter(Device.id.in_(path_nodes)).all()
        dev_by_id = {d.id: d for d in devs}
        node_set = set(path_nodes)
        links = (
            self.db.query(Link)
            .filter(
                Link.status.in_(["active", "up"])
                & (
                    (Link.source_device_id.in_(node_set) & Link.target_device_id.in_(node_set))
                    | (Link.target_device_id.in_(node_set) & Link.source_device_id.in_(node_set))
                )
            )
            .all()
        )
        link_by_pair: Dict[frozenset[int], Link] = {}
        for l in links:
            k = frozenset([l.source_device_id, l.target_device_id])
            if k not in link_by_pair:
                link_by_pair[k] = l

        formatted_path = []
        for i, node_id in enumerate(path_nodes):
            dev = dev_by_id.get(node_id)
            # Determine interfaces for visual clarity
            # Logic: Find link connecting current node to next node
            egress = None
            ingress = None
            
            if i < len(path_nodes) - 1:
                next_id = path_nodes[i+1]
                link = link_by_pair.get(frozenset([node_id, next_id]))
                if link:
                    egress = link.source_interface_name if link.source_device_id == node_id else link.target_interface_name

            if i > 0:
                prev_id = path_nodes[i-1]
                link = link_by_pair.get(frozenset([prev_id, node_id]))
                if link:
                    ingress = link.target_interface_name if link.target_device_id == node_id else link.source_interface_name
            
            # Special case for first/last
            if i == 0: ingress = ingress_intf.name if ingress_intf else "Client"
            if i == len(path_nodes) - 1: egress = egress_intf.name if egress_intf else "Host"

            formatted_path.append(self._format_node(dev, ingress, egress))

        base = {**result_meta, "status": "success", "mode": "bfs", "path": formatted_path}
        return self._add_segments(self._try_extend_l2(base, egress_device, dst_ip, egress_intf))

    def _add_segments(self, result: Dict[str, Any]) -> Dict[str, Any]:
        path = result.get("path")
        if not isinstance(path, list) or not path:
            result = dict(result)
            result.setdefault("segments", [])
            result.setdefault("path_node_ids", [])
            return result

        segments: List[Dict[str, Any]] = []
        node_ids: List[int] = []
        for i, n in enumerate(path):
            if isinstance(n, dict) and n.get("id") is not None:
                try:
                    node_ids.append(int(n["id"]))
                except Exception:
                    pass
            if i >= len(path) - 1:
                continue
            a = path[i]
            b = path[i + 1]
            if not isinstance(a, dict) or not isinstance(b, dict):
                continue
            if a.get("id") is None or b.get("id") is None:
                continue
            seg = {
                "hop": i,
                "from_id": a.get("id"),
                "to_id": b.get("id"),
                "from_port": a.get("egress_intf"),
                "to_port": b.get("ingress_intf"),
            }
            try:
                link = self._find_link(int(a.get("id")), int(b.get("id")))
            except Exception:
                link = None
            if link:
                seg["link"] = {
                    "id": link.id,
                    "status": link.status,
                    "source_device_id": link.source_device_id,
                    "target_device_id": link.target_device_id,
                    "source_interface_name": link.source_interface_name,
                    "target_interface_name": link.target_interface_name,
                }
            segments.append(seg)

        result = dict(result)
        result["segments"] = segments
        result["path_node_ids"] = node_ids
        return result

    def _trace_path_l3(
        self,
        ingress_device: Device,
        egress_device: Device,
        ingress_intf: Optional[Interface],
        egress_intf: Optional[Interface],
        dst_ip: str,
        max_hops: int = 20,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve hop-by-hop path using live L3 route lookups (show ip route dst_ip).
        Uses topology links to map outgoing interface -> next device.
        Returns None if resolution cannot proceed (so caller can fallback to BFS).
        """
        current = ingress_device
        path: List[Dict[str, Any]] = []
        visited = set()
        last_ingress_name = ingress_intf.name if ingress_intf else "Client"

        for _ in range(max_hops):
            if current.id in visited:
                return {
                    "status": "partial",
                    "message": "Routing loop detected during L3 trace.",
                    "mode": "l3",
                    "path": path + [self._format_node(current, last_ingress_name, None)],
                }
            visited.add(current.id)

            if current.id == egress_device.id:
                path.append(self._format_node(current, last_ingress_name, egress_intf.name if egress_intf else "Host"))
                return {"status": "success", "mode": "l3", "path": path}

            route_hint = self._get_route_hint(current, dst_ip, last_ingress_name)
            out_intf = (route_hint.get("outgoing_interface") or "").strip()
            next_hop_ip = (route_hint.get("next_hop_ip") or "").strip()
            vrf = (route_hint.get("vrf") or "").strip() or None

            arp_hint = None
            mac_hint = None
            if not out_intf:
                out_intf, arp_hint, mac_hint = self._resolve_outgoing_interface_via_arp_mac(current, dst_ip, next_hop_ip, vrf)

            if not out_intf and not next_hop_ip:
                return None

            next_device_id, next_ingress_intf = self._resolve_next_hop_by_topology(current.id, out_intf, next_hop_ip)
            if not next_device_id:
                return None

            node = self._format_node(current, last_ingress_name, out_intf or None)
            node["evidence"] = {
                "type": "route_lookup",
                "protocol": route_hint.get("protocol"),
                "next_hop_ip": route_hint.get("next_hop_ip"),
                "outgoing_interface": route_hint.get("outgoing_interface"),
                "vrf": vrf,
                "arp": arp_hint,
                "mac": mac_hint,
            }
            path.append(node)
            last_ingress_name = next_ingress_intf or None
            current = self.db.get(Device, next_device_id)
            if not current:
                return None

        return {
            "status": "partial",
            "message": "Max hop limit reached during L3 trace.",
            "mode": "l3",
            "path": path,
        }

    def _get_route_hint(self, device: Device, dst_ip: str, ingress_interface_name: Optional[str] = None) -> Dict[str, Any]:
        if not device or not getattr(device, "ssh_password", None):
            return {"next_hop_ip": None, "outgoing_interface": None, "protocol": None, "raw": None}

        from app.services.ssh_service import DeviceConnection, DeviceInfo

        dev_info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)
        if not conn.connect():
            return {"next_hop_ip": None, "outgoing_interface": None, "protocol": None, "raw": None}
        try:
            hint = conn.get_route_to(dst_ip)
            if hint.get("outgoing_interface") or hint.get("next_hop_ip"):
                return hint

            candidates: List[str] = []
            if ingress_interface_name:
                cache_key = (device.id, ingress_interface_name)
                if cache_key in self._intf_vrf_cache:
                    v = self._intf_vrf_cache[cache_key]
                else:
                    v = conn.get_interface_vrf(ingress_interface_name).get("vrf")
                    self._intf_vrf_cache[cache_key] = v
                if v:
                    candidates.append(v)

            inferred_intf = self._find_best_interface_name_on_device(device.id, dst_ip)
            if inferred_intf:
                cache_key = (device.id, inferred_intf)
                if cache_key in self._intf_vrf_cache:
                    v = self._intf_vrf_cache[cache_key]
                else:
                    v = conn.get_interface_vrf(inferred_intf).get("vrf")
                    self._intf_vrf_cache[cache_key] = v
                if v and v not in candidates:
                    candidates.append(v)

            for v in candidates:
                h2 = conn.get_route_to(dst_ip, vrf=v)
                if h2.get("outgoing_interface") or h2.get("next_hop_ip"):
                    return h2

            vrfs = self._vrf_list_cache.get(device.id)
            if vrfs is None:
                vrfs = conn.get_vrfs()
                self._vrf_list_cache[device.id] = vrfs

            for v in vrfs:
                if v in candidates:
                    continue
                h2 = conn.get_route_to(dst_ip, vrf=v)
                if h2.get("outgoing_interface") or h2.get("next_hop_ip"):
                    return h2

            return hint
        finally:
            conn.disconnect()

    def _find_best_interface_name_on_device(self, device_id: int, target_ip: str) -> Optional[str]:
        cache_key = (device_id, target_ip)
        if cache_key in self._device_best_intf_cache:
            return self._device_best_intf_cache[cache_key]

        try:
            target = ipaddress.ip_address(target_ip)
        except ValueError:
            self._device_best_intf_cache[cache_key] = None
            return None

        interfaces = (
            self.db.query(Interface)
            .filter(Interface.device_id == device_id)
            .filter(Interface.ip_address.isnot(None))
            .all()
        )

        best_name = None
        best_prefix_len = -1
        for intf in interfaces:
            ip_addr = intf.ip_address
            if not ip_addr:
                continue
            try:
                if "/" in ip_addr:
                    net = ipaddress.ip_network(ip_addr, strict=False)
                else:
                    continue
                if target in net and net.prefixlen > best_prefix_len:
                    best_prefix_len = net.prefixlen
                    best_name = intf.name
            except ValueError:
                continue

        self._device_best_intf_cache[cache_key] = best_name
        return best_name

    def _try_extend_l2(
        self,
        result: Dict[str, Any],
        egress_device: Device,
        dst_ip: str,
        egress_intf: Optional[Interface],
    ) -> Dict[str, Any]:
        path = result.get("path")
        if not isinstance(path, list) or not path:
            return result

        last = path[-1]
        if not isinstance(last, dict) or last.get("id") != egress_device.id:
            return result

        vrf = None
        if isinstance(last.get("evidence"), dict):
            vrf = last["evidence"].get("vrf") or None

        l2_nodes, updated_egress = self._trace_l2_chain_to_host(egress_device, dst_ip, vrf, max_hops=10)
        if updated_egress:
            last["egress_intf"] = updated_egress
            last.setdefault("evidence", {})
            if isinstance(last["evidence"], dict):
                last["evidence"]["l2_extend"] = {"host_ip": dst_ip, "first_port": updated_egress}

        if l2_nodes:
            result = dict(result)
            result["path"] = path + l2_nodes
            result["l2_extended"] = True
        return result

    def _trace_l2_chain_to_host(
        self,
        start_device: Device,
        host_ip: str,
        vrf: Optional[str],
        max_hops: int = 10,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        if not start_device or not getattr(start_device, "ssh_password", None):
            return [], None

        try:
            from app.services.ssh_service import DeviceConnection, DeviceInfo
        except ModuleNotFoundError:
            return [], None

        dev_info = DeviceInfo(
            host=start_device.ip_address,
            username=start_device.ssh_username or "admin",
            password=start_device.ssh_password,
            secret=start_device.enable_password,
            port=int(start_device.ssh_port or 22),
            device_type=start_device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)
        if not conn.connect():
            return [], None
        try:
            arp = conn.get_arp_entry(host_ip, vrf=vrf)
            mac = (arp.get("mac") or "").strip()
            if not mac:
                return [], None
            mac0 = conn.get_mac_table_port(mac, vrf=vrf)
            port0 = (mac0.get("port") or "").strip() or None
            if not port0:
                return [], None
        finally:
            conn.disconnect()

        nodes: List[Dict[str, Any]] = []
        visited = {start_device.id}
        current_device_id = start_device.id
        current_out_port = port0
        current_in_port = None

        for _ in range(max_hops):
            next_device_id, next_ingress = self._resolve_next_hop_by_topology(current_device_id, current_out_port, "")
            if not next_device_id:
                break
            if next_device_id in visited:
                break
            visited.add(next_device_id)

            dev = self.db.query(Device).get(next_device_id)
            if not dev:
                break

            try:
                dev_info = DeviceInfo(
                    host=dev.ip_address,
                    username=dev.ssh_username or "admin",
                    password=dev.ssh_password,
                    secret=dev.enable_password,
                    port=int(dev.ssh_port or 22),
                    device_type=dev.device_type or "cisco_ios",
                )
                conn = DeviceConnection(dev_info)
                if not conn.connect():
                    break
                try:
                    mac_info = conn.get_mac_table_port(mac, vrf=vrf)
                    out_port = (mac_info.get("port") or "").strip() or None
                finally:
                    conn.disconnect()
            except Exception:
                break

            node = self._format_node(dev, next_ingress, out_port)
            node["evidence"] = {"type": "l2_mac_trace", "mac": mac, "learned_port": out_port}
            nodes.append(node)

            if not out_port:
                break

            current_device_id = next_device_id
            current_out_port = out_port
            current_in_port = next_ingress

            nxt, _ = self._resolve_next_hop_by_topology(current_device_id, current_out_port, "")
            if not nxt:
                break

        return nodes, port0

    def _resolve_outgoing_interface_via_arp_mac(
        self,
        device: Device,
        dst_ip: str,
        next_hop_ip: str,
        vrf: Optional[str],
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if not device or not getattr(device, "ssh_password", None):
            return None, None, None

        from app.services.ssh_service import DeviceConnection, DeviceInfo

        dev_info = DeviceInfo(
            host=device.ip_address,
            username=device.ssh_username or "admin",
            password=device.ssh_password,
            secret=device.enable_password,
            port=int(device.ssh_port or 22),
            device_type=device.device_type or "cisco_ios",
        )
        conn = DeviceConnection(dev_info)
        if not conn.connect():
            return None, None, None
        try:
            arp_target = next_hop_ip or dst_ip
            arp = conn.get_arp_entry(arp_target, vrf=vrf)
            mac = (arp.get("mac") or "").strip()
            if not mac:
                return (arp.get("interface") or None), arp, None

            mac_info = conn.get_mac_table_port(mac, vrf=vrf)
            port = (mac_info.get("port") or "").strip()
            if port:
                return port, arp, mac_info
            return (arp.get("interface") or None), arp, mac_info
        finally:
            conn.disconnect()

    def _normalize_intf_key(self, name: str) -> str:
        if not name:
            return ""
        s = name.strip().lower().replace(" ", "")
        mapping = {
            "gi": "gigabitethernet",
            "fa": "fastethernet",
            "te": "tengigabitethernet",
            "fo": "fortygigabitethernet",
            "hu": "hundredgigabitethernet",
            "po": "port-channel",
            "vl": "vlan",
            "eth": "ethernet",
        }
        for short, full in mapping.items():
            if s.startswith(short) and not s.startswith(full):
                rest = s[len(short):]
                if rest and (rest[0].isdigit() or rest[0] == "/"):
                    return full + rest
        return s

    def _resolve_next_hop_by_topology(
        self, current_device_id: int, outgoing_interface: str, next_hop_ip: str
    ) -> Tuple[Optional[int], Optional[str]]:
        """
        Returns (next_device_id, ingress_interface_name_on_next_device)
        """
        out_key = self._normalize_intf_key(outgoing_interface)
        links = self._get_links_for_device(current_device_id)

        for l in links:
            if l.source_device_id == current_device_id:
                if self._normalize_intf_key(l.source_interface_name) == out_key:
                    return l.target_device_id, l.target_interface_name
            if l.target_device_id == current_device_id:
                if self._normalize_intf_key(l.target_interface_name) == out_key:
                    return l.source_device_id, l.source_interface_name

        if next_hop_ip:
            dev = self.db.query(Device).filter(Device.ip_address == next_hop_ip).first()
            if dev:
                link = self._find_link(current_device_id, dev.id)
                if link:
                    ingress = link.target_interface_name if link.target_device_id == dev.id else link.source_interface_name
                    return dev.id, ingress

        return None, None

    def _find_device_by_ip(self, target_ip: str) -> (Optional[Device], Optional[Interface]):
        """
        Find the device that owns the subnet of the target IP.
        """
        try:
            target = ipaddress.ip_address(target_ip)
        except ValueError:
            return None, None

        if self._l3_interfaces_cache is None:
            self._l3_interfaces_cache = (
                self.db.query(Interface)
                .options(selectinload(Interface.device))
                .filter(Interface.ip_address.isnot(None))
                .all()
            )
        interfaces = self._l3_interfaces_cache
        
        best_match = None
        best_device = None
        best_prefix_len = -1

        for intf in interfaces:
            if not intf.ip_address: continue
            try:
                # Assume format "1.1.1.1/24" or just "1.1.1.1" (implies /32)
                if "/" in intf.ip_address:
                    net = ipaddress.ip_network(intf.ip_address, strict=False)
                else:
                     # Skip if no subnet mask info (or treat as host /32)
                     # For exact match:
                     if intf.ip_address == target_ip:
                         return intf.device, intf
                     continue

                if target in net:
                    if net.prefixlen > best_prefix_len:
                        best_prefix_len = net.prefixlen
                        best_match = intf
                        best_device = intf.device
            except ValueError:
                continue
        
        if best_device:
            return best_device, best_match

        dev = self.db.query(Device).filter(Device.ip_address == target_ip).first()
        if dev:
            return dev, Interface(name="Mgmt", ip_address=target_ip, device_id=dev.id)

        return None, None

    def _find_shortest_path(self, start_id: int, end_id: int) -> List[int]:
        """
        BFS to find shortest list of device IDs.
        """
        queue = deque([[start_id]])
        visited = {start_id}
        graph = self._build_adjacency_list()

        while queue:
            path = queue.popleft()
            node = path[-1]
            
            if node == end_id:
                return path
            
            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
        return []

    def _build_adjacency_list(self) -> Dict[int, List[int]]:
        if self._adjacency_cache is not None:
            return self._adjacency_cache
        links = self.db.query(Link).filter(Link.status.in_(["active", "up"])).all()
        adj: Dict[int, List[int]] = {}
        for link in links:
            if link.source_device_id not in adj: adj[link.source_device_id] = []
            if link.target_device_id not in adj: adj[link.target_device_id] = []
            
            adj[link.source_device_id].append(link.target_device_id)
            adj[link.target_device_id].append(link.source_device_id)
        self._adjacency_cache = adj
        return adj

    def _get_links_for_device(self, device_id: int) -> List[Link]:
        cached = self._links_by_device_cache.get(device_id)
        if cached is not None:
            return cached
        links = (
            self.db.query(Link)
            .filter(
                (Link.status.in_(["active", "up"]))
                & ((Link.source_device_id == device_id) | (Link.target_device_id == device_id))
            )
            .all()
        )
        self._links_by_device_cache[device_id] = links
        return links

    def _find_link(self, node_a: int, node_b: int) -> Optional[Link]:
        return self.db.query(Link).filter(
            or_(
                (Link.source_device_id == node_a) & (Link.target_device_id == node_b),
                (Link.source_device_id == node_b) & (Link.target_device_id == node_a)
            )
        ).first()

    def _format_node(self, device: Device, ingress: str = None, egress: str = None) -> Dict[str, Any]:
        if not device: return {"name": "Unknown"}
        return {
            "id": device.id,
            "name": device.name,
            "type": device.device_type,
            "ip": device.ip_address,
            "ingress_intf": ingress,
            "egress_intf": egress,
            "role": device.role
        }
