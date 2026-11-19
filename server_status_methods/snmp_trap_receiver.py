import sys
import asyncio
from pysnmp.entity import engine, config
from pysnmp.carrier.asyncio.dgram import udp
from pysnmp.entity.rfc3413 import ntfrcv

def run_trap_receiver(port=162):
    # Ensure there is an active event loop in this thread
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    snmp_engine = engine.SnmpEngine()
    
    # Configure community 'public' for SNMPv1/v2c Traps
    config.add_v1_system(snmp_engine, 'tms-area', 'public')
    
    try:
        # Bind transport endpoint to listen on UDP Port
        config.add_transport(
            snmp_engine,
            udp.DOMAIN_NAME,
            udp.UdpTransport().openServerMode(('0.0.0.0', port))
        )
        print(f"==================================================")
        print(f"      SNMP TRAP RECEIVER RUNNING ON UDP PORT {port}")
        print(f"      Mendengarkan Trap alert dari GDC IMB...")
        print(f"==================================================")
    except Exception as e:
        print(f"[ERROR] Gagal bind ke UDP port {port}: {e}")
        if port == 162:
            print("Mencoba menggunakan port cadangan 1620...")
            run_trap_receiver(1620)
        return

    # Callback function for received notifications
    def cb_fun(snmp_engine, state_reference, context_engine_id, context_name, var_binds, cb_ctx):
        print("\n[NOTIFICATION RECEIVED] Trap Packet Diterima:")
        for name, val in var_binds:
            oid_str = name.prettyPrint()
            val_str = val.prettyPrint()
            print(f"  {oid_str} = {val_str}")
            
            # Simple highlight if it contains GDC specific values
            if "28713" in oid_str:
                print("  --> [GDC CUSTOM OID DETECTED]")

    # Register Notification Receiver with the engine
    ntfrcv.NotificationReceiver(snmp_engine, cb_fun)
    
    # Run the event loop
    try:
        snmp_engine.transportDispatcher.jobStarted(1)
        snmp_engine.transportDispatcher.runDispatcher()
    except KeyboardInterrupt:
        print("\nStopping SNMP Trap Receiver...")
        snmp_engine.transportDispatcher.closeDispatcher()
    except Exception as e:
        print(f"[ERROR] dispatcher error: {e}")

if __name__ == "__main__":
    port_to_bind = 162
    if len(sys.argv) > 1:
        try:
            port_to_bind = int(sys.argv[1])
        except:
            pass
    run_trap_receiver(port_to_bind)
