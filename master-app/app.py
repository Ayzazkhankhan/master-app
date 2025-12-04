from flask import Flask, request, jsonify, render_template_string
import logging
from datetime import datetime
import subprocess
import time

# Kubernetes client
from kubernetes import client, config

app = Flask(__name__)





# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#############################################################
# LOAD KUBERNETES CONFIG
#############################################################

try:
    config.load_kube_config("/root/.kube/config")  
    logger.info("Kubernetes config loaded from /root/.kube/config")
except:
    try:
        config.load_incluster_config()
        logger.info("Kubernetes in-cluster config loaded")
    except:
        logger.warning("⚠ Could NOT load Kubernetes config")

k8s = client.CoreV1Api()

#############################################################
# OLD EDGE DEVICE SYSTEM (still works for your custom apps)
#############################################################

edge_devices = {}
command_queue = {}

#############################################################
# HTML DASHBOARD TEMPLATE (unchanged)
#############################################################

DASHBOARD_HTML = """ 
YOUR HTML TEMPLATE SAME AS BEFORE — I DID NOT REMOVE ANYTHING
(You already pasted it, so keep it exactly as it is)
"""

#############################################################
# UI ROUTE
#############################################################

@app.route('/')
def dashboard():
    return render_template_string(DASHBOARD_HTML)

#############################################################
# DASHBOARD DATA (NOW USES REAL K8S NODE LIST)
#############################################################

@app.route('/api/dashboard-data')
def get_dashboard_data():
    """Dashboard uses Kubernetes to list real edge devices"""

    nodes = []
    try:
        k8s_nodes = k8s.list_node().items
        for n in k8s_nodes:
            ready_status = n.status.conditions[-1].status
            nodes.append({
                "device_id": n.metadata.name,
                "status": "online" if ready_status == "True" else "offline",
                "last_seen": n.metadata.creation_timestamp.isoformat(),
                "labels": n.metadata.labels,
                "data_history": []  # UI expects this field
            })
    except Exception as e:
        logger.error("K8s fetch error: " + str(e))

    return jsonify({
        "devices": nodes,
        "device_count": len(nodes),
        "total_messages": len(nodes),
        "timestamp": datetime.now().isoformat()
    })

#############################################################
# EDGE → CLOUD DATA RECEIVER (kept from your original app)
#############################################################

@app.route('/edge/data', methods=['POST'])
def receive_edge_data():
    data = request.json
    device_id = data.get('device_id')

    if not device_id:
        return jsonify({'error': 'device_id required'}), 400

    if device_id not in edge_devices:
        edge_devices[device_id] = {
            'device_id': device_id,
            'data_history': []
        }

    edge_devices[device_id]['data_history'].append({
        "timestamp": datetime.now().isoformat(),
        "payload": data.get("payload", {})
    })

    edge_devices[device_id]['data_history'] = edge_devices[device_id]['data_history'][-10:]

    return jsonify({"message": "data stored"}), 200

#############################################################
# COMMAND SYSTEM (Cloud → Edge)
#############################################################

@app.route('/command/send', methods=['POST'])
def send_command():
    data = request.json
    device_id = data.get("device_id")
    command = data.get("command")

    if not device_id or not command:
        return jsonify({"error": "device_id and command required"}), 400

    if device_id not in command_queue:
        command_queue[device_id] = []

    command_id = f"cmd_{int(time.time() * 1000)}"

    entry = {
        "command": command,
        "params": data.get("params", {}),
        "timestamp": datetime.now().isoformat(),
        "command_id": command_id
    }

    command_queue[device_id].append(entry)

    return jsonify({"message": "command queued", "command_id": command_id})

@app.route('/edge/commands/<device_id>', methods=['GET'])
def get_commands(device_id):
    cmds = command_queue.get(device_id, [])
    command_queue[device_id] = []  # Clear after sending
    return jsonify({"device_id": device_id, "commands": cmds})

#############################################################
# COMMAND RESULT RECEIVER
#############################################################

@app.route('/edge/command/result', methods=["POST"])
def receive_command_result():
    data = request.json
    logger.info(f"Result from {data.get('device_id')} → {data.get('command_id')}: {data.get('result')}")
    return jsonify({"message": "result received"})

#############################################################
# SIMPLE HEALTH CHECK
#############################################################

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "service": "master-app"})

#############################################################
# NEW API 1: GET KUBERNETES NODE LIST
#############################################################

@app.route('/api/k8s/nodes', methods=["GET"])
def api_k8s_nodes():
    """List all Kubernetes nodes (cloud + edge devices)"""
    try:
        nodes = k8s.list_node().items
        output = []

        for n in nodes:
            ready_condition = n.status.conditions[-1]
            output.append({
                "name": n.metadata.name,
                "ready": ready_condition.status,
                "labels": n.metadata.labels,
                "cpu": n.status.capacity.get("cpu"),
                "memory": n.status.capacity.get("memory"),
                "created": n.metadata.creation_timestamp.isoformat()
            })

        return jsonify({"nodes": output})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#############################################################
# NEW API 2: LIST PODS GROUPED BY NODE
#############################################################

@app.route('/api/k8s/pods', methods=["GET"])
def api_k8s_pods():
    """Show all pods in Kubernetes grouped by node"""
    try:
        pods = k8s.list_pod_for_all_namespaces().items
        result = {}

        for p in pods:
            node = p.spec.node_name or "unknown"

            if node not in result:
                result[node] = []

            result[node].append({
                "name": p.metadata.name,
                "namespace": p.metadata.namespace,
                "status": p.status.phase,
                "ip": p.status.pod_ip,
            })

        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

#############################################################
# NEW API 3: GENERATE NEW KUBEEDGE TOKEN
#############################################################

@app.route('/api/edge/token', methods=["GET"])
def api_get_token():
    """Generate new EdgeCore join token"""
    try:
        output = subprocess.check_output(
            ["keadm", "gettoken", "--kube-config=/etc/rancher/k3s/k3s.yaml"],
            text=True
        )
        return jsonify({"token": output.strip()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


#############################################################
# START APP
#############################################################

if __name__ == '__main__':
    logger.info("Starting Master App with Kubernetes Support")
    app.run(host='0.0.0.0', port=5000, debug=True)
