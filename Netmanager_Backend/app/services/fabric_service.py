from sqlalchemy.orm import Session
from app.models.device import Device
from typing import List, Dict, Any

class FabricService:
    def __init__(self, db: Session):
        self.db = db

    def generate_fabric_config(self, 
                               spines: List[int], 
                               leafs: List[int], 
                               asn_base: int = 65000, 
                               vni_base: int = 10000, 
                               underlay_ospf_area: int = 0) -> Dict[int, str]:
        """
        Generate VXLAN BGP EVPN Configuration for a Spine-Leaf Fabric.
        Returns a dict of {device_id: config_string}.
        """
        configs = {}
        
        spine_devices = self.db.query(Device).filter(Device.id.in_(spines)).all()
        leaf_devices = self.db.query(Device).filter(Device.id.in_(leafs)).all()
        
        # Simple IP Allocation Logic (Simulation)
        # Loopbacks: 10.0.0.X/32
        # P2P Links: 10.1.X.Y/30
        
        # 1. Generate Spine Configs
        for i, spine in enumerate(spine_devices):
            rid = f"10.0.0.{10+i}"
            config = self._render_spine(spine, rid, asn_base, leaf_devices)
            configs[spine.id] = config
            
        # 2. Generate Leaf Configs
        for i, leaf in enumerate(leaf_devices):
            rid = f"10.0.0.{20+i}"
            config = self._render_leaf(leaf, rid, asn_base, spine_devices, vni_base)
            configs[leaf.id] = config
            
        return configs

    def _render_spine(self, device, rid, asn, leafs):
        # BGP Listen Range for Leafs
        bgp_listen = "10.0.0.0/24" 
        
        return f"""! Generated Spine Config for {device.name}
hostname {device.hostname or device.name}
!
interface Loopback0
 ip address {rid} 255.255.255.255
 ip ospf 1 area 0
!
router ospf 1
 router-id {rid}
!
router bgp {asn}
 bgp router-id {rid}
 bgp log-neighbor-changes
 neighbor leaves peer-group
 neighbor leaves remote-as {asn}
 neighbor leaves update-source Loopback0
 !
 address-family l2vpn evpn
  neighbor leaves send-community both
  neighbor leaves route-reflector-client
 exit-address-family
!
! Dynamic Neighbors (simplified)
! In real world, we define neighbor statements or listen range
!
"""

    def _render_leaf(self, device, rid, asn, spines, vni_base):
        
        # Config Builder
        lines = []
        lines.append(f"! Generated Leaf Config for {device.name}")
        lines.append(f"hostname {device.hostname or device.name}")
        lines.append("!")
        lines.append("feature ospf")
        lines.append("feature bgp")
        lines.append("feature interface-vlan")
        lines.append("feature vn-segment-vlan-based")
        lines.append("feature nv overlay")
        lines.append("nv overlay evpn")
        lines.append("!")
        
        # Loopbacks
        lines.append("interface Loopback0")
        lines.append(f"  ip address {rid}/32")
        lines.append("  ip router ospf 1 area 0")
        lines.append("!")
        lines.append("interface Loopback1")
        lines.append(f"  description VTEP Source")
        lines.append(f"  ip address {rid.replace('10.0.0.', '10.0.1.')}/32")
        lines.append("  ip router ospf 1 area 0")
        lines.append("!")
        
        # Underlay
        lines.append("router ospf 1")
        lines.append(f"  router-id {rid}")
        lines.append("!")
        
        # Overlay
        lines.append(f"router bgp {asn}")
        lines.append(f"  router-id {rid}")
        for spine in spines:
             # Assuming we know spine loopbacks, here we hardcode for demo
             # Real logic needs precise IP tracking
             spine_rid = "10.0.0.10" # Placeholder
             lines.append(f"  neighbor {spine_rid}")
             lines.append(f"    remote-as {asn}")
             lines.append("    update-source Loopback0")
             lines.append("    address-family l2vpn evpn")
             lines.append("      send-community both")
        lines.append("!")
        
        # NVE
        lines.append("interface nve1")
        lines.append("  no shutdown")
        lines.append("  source-interface Loopback1")
        lines.append("  host-reachability protocol bgp")
        
        return "\n".join(lines)
