from flask import Flask, request, jsonify, render_template_string, send_file
import logging
from datetime import datetime
import subprocess
import time
import os


# Kubernetes client
from kubernetes import client, config
from kubernetes.client.rest import ApiException

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for custom edge devices and command queues (keeps backward compatibility)
edge_devices = {}
command_queue = {}

# Try to load kubeconfig (first tries in-cluster, then fallback path)
k8s = None
try:
    config.load_incluster_config()
    logger.info("Loaded in-cluster Kubernetes config")
except Exception:
    try:
        kubeconf = os.path.expanduser("~/.kube/config")
        config.load_kube_config(kubeconf)
        logger.info(f"Loaded kubeconfig from {kubeconf}")
    except Exception as e:
        logger.warning("Could not load any Kubernetes config: " + str(e))

if config and hasattr(config, "load_kube_config"):
    try:
        k8s = client.CoreV1Api()
    except Exception as e:
        logger.warning("Failed to create CoreV1Api client: " + str(e))

# HTML Dashboard Template (your full UI — unchanged)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Master App Dashboard</title>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .header {
            background: white;
            padding: 30px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            margin-bottom: 30px;
            text-align: center;
        }
        h1 {
            color: #667eea;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .status-badge {
            display: inline-block;
            padding: 8px 20px;
            background: #10b981;
            color: white;
            border-radius: 20px;
            font-weight: bold;
            margin-top: 10px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
        }
        .card h2 {
            color: #667eea;
            margin-bottom: 20px;
            font-size: 1.5em;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        .device-list {
            list-style: none;
        }
        .device-item {
            background: #f3f4f6;
            padding: 15px;
            margin-bottom: 10px;
            border-radius: 10px;
            border-left: 4px solid #667eea;
        }
        .device-item.offline {
            border-left-color: #ef4444;
            opacity: 0.6;
        }
        .device-name {
            font-weight: bold;
            color: #1f2937;
            font-size: 1.1em;
            margin-bottom: 5px;
        }
        .device-info {
            color: #6b7280;
            font-size: 0.9em;
            margin-top: 5px;
        }
        .sensor-data {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin-top: 10px;
        }
        .sensor-item {
            background: white;
            padding: 10px;
            border-radius: 8px;
            text-align: center;
        }
        .sensor-label {
            color: #6b7280;
            font-size: 0.85em;
            margin-bottom: 5px;
        }
        .sensor-value {
            color: #667eea;
            font-size: 1.3em;
            font-weight: bold;
        }
        .command-form {
            background: #f9fafb;
            padding: 20px;
            border-radius: 10px;
            margin-top: 15px;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #374151;
            font-weight: 600;
        }
        select, input, textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e5e7eb;
            border-radius: 8px;
            font-size: 1em;
            transition: border-color 0.3s;
        }
        select:focus, input:focus, textarea:focus {
            outline: none;
            border-color: #667eea;
        }
        button {
            background: #667eea;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 8px;
            font-size: 1em;
            font-weight: bold;
            cursor: pointer;
            transition: background 0.3s;
            width: 100%;
        }
        button:hover {
            background: #5568d3;
        }
        .message-log {
            max-height: 400px;
            overflow-y: auto;
            background: #f9fafb;
            padding: 15px;
            border-radius: 10px;
        }
        .message-item {
            background: white;
            padding: 12px;
            margin-bottom: 10px;
            border-radius: 8px;
            border-left: 4px solid #10b981;
        }
        .message-item.command {
            border-left-color: #f59e0b;
        }
        .message-time {
            color: #6b7280;
            font-size: 0.85em;
        }
        .message-content {
            color: #1f2937;
            margin-top: 5px;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 15px;
            margin-bottom: 20px;
        }
        .stat-card {
            background: white;
            padding: 20px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.2);
            text-align: center;
        }
        .stat-value {
            font-size: 2.5em;
            font-weight: bold;
            color: #667eea;
        }
        .stat-label {
            color: #6b7280;
            margin-top: 5px;
        }
        .refresh-info {
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 0.9em;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .loading {
            animation: pulse 2s infinite;
        }

        /* small helpers for pods/logs display on the UI if needed later */
        .pod-list { margin-top: 10px; }
        .pod-item { background:#fff;padding:8px;border-radius:8px;margin-bottom:6px;border-left:4px solid #9CA3AF; }
        .btn-small { padding:6px 10px;font-size:0.9em;border-radius:6px;cursor:pointer;background:#667eea;color:#fff;border:none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🌥️ Master App Dashboard</h1>
            <div class="status-badge">Cloud Service Running</div>
        </div>

        <div class="stats">
            <div class="stat-card">
                <div class="stat-value" id="deviceCount">0</div>
                <div class="stat-label">Connected Devices</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="messageCount">0</div>
                <div class="stat-label">Messages Received</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="commandCount">0</div>
                <div class="stat-label">Commands Sent</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h2>📱 Connected Edge Devices</h2>
                <ul class="device-list" id="deviceList">
                    <li style="color: #6b7280; text-align: center; padding: 20px;">
                        No devices connected yet...
                    </li>
                </ul>
            </div>

            <div class="card">
                <h2>🎮 Send Command to Edge</h2>
                <div class="command-form">
                    <div class="form-group">
                        <label>Select Device</label>
                        <select id="deviceSelect">
                            <option value="">No devices available</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Command</label>
                        <select id="commandSelect">
                            <option value="get_status">Get Status</option>
                            <option value="restart_service">Restart Service</option>
                            <option value="collect_logs">Collect Logs</option>
                            <option value="set_threshold">Set Threshold</option>
                            <option value="update_config">Update Config</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Parameters (JSON)</label>
                        <textarea id="commandParams" rows="3" placeholder='{"service": "sensor-monitor"}'>{}</textarea>
                    </div>
                    <button onclick="sendCommand()">Send Command</button>
                    <div style="margin-top:10px;">
                        <button class="btn-small" onclick="refreshNow()">Refresh Now</button>
                        <button class="btn-small" onclick="openToken()">Generate Token</button>
                    </div>
                    <div id="tokenArea" style="margin-top:10px;color:#111;"></div>
                </div>
            </div>
        </div>

        <div class="card">
            <h2>📊 Recent Activity</h2>
            <div class="message-log" id="activityLog">
                <div style="color: #6b7280; text-align: center; padding: 20px;">
                    Waiting for activity...
                </div>
            </div>
        </div>

        <div class="refresh-info">
            Auto-refreshing every 3 seconds • Last updated: <span id="lastUpdate">-</span>
        </div>
    </div>

    <script>
        let messageCount = 0;
        let commandCount = 0;
        let activityLog = [];

        async function fetchDashboardData() {
            try {
                const response = await fetch('/api/dashboard-data');
                const data = await response.json();
                
                updateDeviceList(data.devices);
                updateStats(data);
                updateLastUpdateTime();
            } catch (error) {
                console.error('Error fetching data:', error);
            }
        }

        function updateDeviceList(devices) {
            const deviceList = document.getElementById('deviceList');
            const deviceSelect = document.getElementById('deviceSelect');
            
            if (!devices || devices.length === 0) {
                deviceList.innerHTML = '<li style="color: #6b7280; text-align: center; padding: 20px;">No devices connected yet...</li>';
                deviceSelect.innerHTML = '<option value="">No devices available</option>';
                return;
            }

            deviceList.innerHTML = devices.map(device => {
                const isOnline = device.status === 'online';
                const latestData = device.data_history && device.data_history.length > 0 
                    ? device.data_history[device.data_history.length - 1].payload 
                    : null;

                let sensorHtml = '';
                if (latestData) {
                    sensorHtml = `
                        <div class="sensor-data">
                            ${latestData.temperature ? `
                                <div class="sensor-item">
                                    <div class="sensor-label">Temperature</div>
                                    <div class="sensor-value">${latestData.temperature}°C</div>
                                </div>
                            ` : ''}
                            ${latestData.humidity ? `
                                <div class="sensor-item">
                                    <div class="sensor-label">Humidity</div>
                                    <div class="sensor-value">${latestData.humidity}%</div>
                                </div>
                            ` : ''}
                            ${latestData.cpu_usage ? `
                                <div class="sensor-item">
                                    <div class="sensor-label">CPU Usage</div>
                                    <div class="sensor-value">${latestData.cpu_usage}%</div>
                                </div>
                            ` : ''}
                            ${latestData.memory_usage ? `
                                <div class="sensor-item">
                                    <div class="sensor-label">Memory</div>
                                    <div class="sensor-value">${latestData.memory_usage}%</div>
                                </div>
                            ` : ''}
                        </div>
                    `;
                }

                return `
                    <li class="device-item ${!isOnline ? 'offline' : ''}">
                        <div class="device-name">${device.device_id}</div>
                        <div class="device-info">
                            Status: <strong>${device.status}</strong> | 
                            Last Seen: ${device.last_seen ? new Date(device.last_seen).toLocaleTimeString() : '-'}
                        </div>
                        ${sensorHtml}
                    </li>
                `;
            }).join('');

            deviceSelect.innerHTML = devices.map(device => 
                `<option value="${device.device_id}">${device.device_id}</option>`
            ).join('');
        }

        function updateStats(data) {
            document.getElementById('deviceCount').textContent = data.device_count;
            document.getElementById('messageCount').textContent = data.total_messages;
            document.getElementById('commandCount').textContent = commandCount;
        }

        function updateLastUpdateTime() {
            document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
        }

        async function sendCommand() {
            const deviceId = document.getElementById('deviceSelect').value;
            const command = document.getElementById('commandSelect').value;
            const paramsText = document.getElementById('commandParams').value;

            if (!deviceId) {
                alert('Please select a device');
                return;
            }

            let params = {};
            try {
                params = JSON.parse(paramsText);
            } catch (error) {
                alert('Invalid JSON in parameters field');
                return;
            }

            try {
                const response = await fetch('/command/send', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        device_id: deviceId,
                        command: command,
                        params: params
                    })
                });

                const result = await response.json();
                
                if (response.ok) {
                    commandCount++;
                    addActivityLog(`Command sent to ${deviceId}: ${command}`, 'command');
                    alert('Command sent successfully!');
                } else {
                    alert('Failed to send command: ' + result.error);
                }
            } catch (error) {
                alert('Error sending command: ' + error.message);
            }
        }

        function addActivityLog(message, type = 'info') {
            const logDiv = document.getElementById('activityLog');
            const timestamp = new Date().toLocaleTimeString();
            
            const messageHtml = `
                <div class="message-item ${type}">
                    <div class="message-time">${timestamp}</div>
                    <div class="message-content">${message}</div>
                </div>
            `;
            
            logDiv.innerHTML = messageHtml + logDiv.innerHTML;
            
            // Keep only last 20 messages
            const items = logDiv.querySelectorAll('.message-item');
            if (items.length > 20) {
                items[items.length - 1].remove();
            }
        }

        function refreshNow() {
            fetchDashboardData();
            addActivityLog('Manual refresh triggered', 'info');
        }

        async function openToken() {
            try {
                const res = await fetch('/api/edge/token');
                const data = await res.json();
                if (res.ok && data.token) {
                    document.getElementById('tokenArea').textContent = 'New Token: ' + data.token;
                    addActivityLog('New join token generated', 'info');
                } else {
                    document.getElementById('tokenArea').textContent = 'Token error: ' + (data.error || 'unknown');
                }
            } catch (e) {
                document.getElementById('tokenArea').textContent = 'Token error: ' + e.message;
            }
        }

        // Auto-refresh every 3 seconds
        setInterval(fetchDashboardData, 3000);
        
        // Initial load
        fetchDashboardData();
    </script>
</body>
</html>
"""

@app.route('/')
def dashboard():
    """Main dashboard view"""
    return render_template_string(DASHBOARD_HTML)

# Helper: convert k8s Node to UI-friendly device dict
def _k8s_node_to_device(node):
    try:
        ready_cond = None
        for c in node.status.conditions:
            if c.type == "Ready":
                ready_cond = c
                break
        status = "online" if ready_cond and ready_cond.status == "True" else "offline"
    except Exception:
        status = "unknown"

    return {
        "device_id": node.metadata.name,
        "registered_at": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
        "last_seen": node.metadata.creation_timestamp.isoformat() if node.metadata.creation_timestamp else None,
        "status": status,
        "metadata": {
            "labels": node.metadata.labels
        },
        "data_history": []  # no telemetry from k8s nodes; keep field for UI compatibility
    }

@app.route('/api/dashboard-data')
def get_dashboard_data():
    """
    Dashboard returns a combined list:
    - Registered custom edge devices (edge_devices dict)
    - Kubernetes nodes (k8s)
    This lets your UI show both the IoT devices and cluster nodes.
    """
    devices = []

    # 1) add registered custom devices (first, so they appear)
    for d in edge_devices.values():
        devices.append(d)

    # 2) add Kubernetes nodes (if k8s client available)
    if k8s:
        try:
            nodes = k8s.list_node().items
            for n in nodes:
                devices.append(_k8s_node_to_device(n))
        except Exception as e:
            logger.warning("Cannot list K8s nodes: " + str(e))

    total_messages = sum(len(d.get("data_history", [])) for d in devices)

    return jsonify({
        "devices": devices,
        "device_count": len(devices),
        "total_messages": total_messages,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'master-app',
        'timestamp': datetime.now().isoformat()
    }), 200

@app.route('/edge/register', methods=['POST'])
def register_edge():
    """Register an edge device (legacy / optional)"""
    data = request.json or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({'error': 'device_id required'}), 400

    edge_devices[device_id] = {
        'device_id': device_id,
        'registered_at': datetime.now().isoformat(),
        'last_seen': datetime.now().isoformat(),
        'status': 'online',
        'metadata': data.get('metadata', {}),
        'data_history': edge_devices.get(device_id, {}).get('data_history', [])
    }
    command_queue[device_id] = command_queue.get(device_id, [])
    logger.info(f"Edge device registered: {device_id}")
    return jsonify({'message': 'Device registered successfully', 'device_id': device_id}), 201

@app.route('/edge/data', methods=['POST'])
def receive_edge_data():
    """Receive telemetry from a custom edge device (legacy)"""
    data = request.json or {}
    device_id = data.get('device_id')
    if not device_id:
        return jsonify({'error': 'device_id required'}), 400

    if device_id not in edge_devices:
        edge_devices[device_id] = {
            'device_id': device_id,
            'registered_at': datetime.now().isoformat(),
            'data_history': []
        }

    edge_devices[device_id]['last_seen'] = datetime.now().isoformat()
    edge_devices[device_id]['status'] = 'online'

    edge_devices[device_id].setdefault('data_history', [])
    edge_devices[device_id]['data_history'].append({
        'timestamp': datetime.now().isoformat(),
        'payload': data.get('payload', {})
    })
    edge_devices[device_id]['data_history'] = edge_devices[device_id]['data_history'][-20:]

    logger.info(f"Received data from {device_id}: {data.get('payload', {})}")
    return jsonify({'message': 'Data received successfully', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/edge/commands/<device_id>', methods=['GET'])
def get_commands(device_id):
    """Edge device polls for pending commands (Cloud -> Edge)"""
    if device_id not in command_queue:
        command_queue[device_id] = []
    cmds = command_queue[device_id].copy()
    command_queue[device_id] = []
    logger.info(f"Device {device_id} polled for commands. Sending {len(cmds)} commands")
    return jsonify({'device_id': device_id, 'commands': cmds, 'timestamp': datetime.now().isoformat()}), 200

@app.route('/command/send', methods=['POST'])
def send_command():
    """Queue a command to an edge device"""
    data = request.json or {}
    device_id = data.get('device_id')
    command = data.get('command')
    if not device_id or not command:
        return jsonify({'error': 'device_id and command required'}), 400

    command_entry = {
        'command': command,
        'params': data.get('params', {}),
        'timestamp': datetime.now().isoformat(),
        'command_id': f"cmd_{int(time.time() * 1000)}"
    }
    command_queue.setdefault(device_id, []).append(command_entry)
    logger.info(f"Queued command for {device_id}: {command}")
    return jsonify({'message': 'Command queued successfully', 'command_id': command_entry['command_id']}), 200

@app.route('/edge/command/result', methods=['POST'])
def receive_command_result():
    data = request.json or {}
    logger.info(f"Command result: {data}")
    return jsonify({'message': 'Result received', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/devices', methods=['GET'])
def list_devices():
    """Return registered devices + K8s nodes summary"""
    devices = []
    for d in edge_devices.values():
        devices.append(d)
    if k8s:
        try:
            for n in k8s.list_node().items:
                devices.append(_k8s_node_to_device(n))
        except Exception as e:
            logger.warning("Cannot list nodes: " + str(e))
    return jsonify({'devices': devices, 'count': len(devices)}), 200

@app.route('/device/<device_id>', methods=['GET'])
def get_device_info(device_id):
    """Get a registered edge device or k8s node info"""
    # check registered devices first
    if device_id in edge_devices:
        return jsonify(edge_devices[device_id]), 200

    # check k8s nodes
    if k8s:
        try:
            n = k8s.read_node(device_id)
            return jsonify(_k8s_node_to_device(n)), 200
        except ApiException as e:
            if e.status == 404:
                return jsonify({'error': 'Device not found'}), 404
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Device not found'}), 404

# Kubernetes APIs
@app.route('/api/k8s/nodes', methods=['GET'])
def api_k8s_nodes():
    """List Kubernetes nodes"""
    if not k8s:
        return jsonify({'error': 'Kubernetes client not available'}), 500
    try:
        nodes = k8s.list_node().items
        out = []
        for n in nodes:
            out.append({
                'name': n.metadata.name,
                'labels': n.metadata.labels,
                'creation': n.metadata.creation_timestamp.isoformat() if n.metadata.creation_timestamp else None,
                'status': 'online' if any((c.type == 'Ready' and c.status == 'True') for c in (n.status.conditions or [])) else 'offline',
                'capacity': n.status.capacity
            })
        return jsonify({'nodes': out})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/k8s/pods', methods=['GET'])
def api_k8s_pods():
    """List pods grouped by node"""
    if not k8s:
        return jsonify({'error': 'Kubernetes client not available'}), 500
    try:
        pods = k8s.list_pod_for_all_namespaces().items
        result = {}
        for p in pods:
            node = p.spec.node_name or 'unknown'
            result.setdefault(node, []).append({
                'name': p.metadata.name,
                'namespace': p.metadata.namespace,
                'status': p.status.phase,
                'pod_ip': p.status.pod_ip,
                'host_ip': p.status.host_ip,
                'containers': [c.name for c in (p.spec.containers or [])]
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/k8s/pod/logs', methods=['GET'])
def api_k8s_pod_logs():
    """
    Query params:
      - namespace (default: default)
      - pod (required)
      - container (optional)
      - tail_lines (optional)
    """
    if not k8s:
        return jsonify({'error': 'Kubernetes client not available'}), 500

    namespace = request.args.get('namespace', 'default')
    pod = request.args.get('pod')
    container = request.args.get('container', None)
    tail_lines = int(request.args.get('tail_lines', '200'))

    if not pod:
        return jsonify({'error': 'pod parameter required'}), 400

    try:
        logs = k8s.read_namespaced_pod_log(name=pod, namespace=namespace, container=container, tail_lines=tail_lines)
        return jsonify({'pod': pod, 'namespace': namespace, 'logs': logs})
    except ApiException as e:
        return jsonify({'error': f"K8s API error: {e}"}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/edge/token', methods=['GET'])
def api_get_token():
    """Generate new KubeEdge join token via keadm (must be available on host)"""
    try:
        # keadm must be installed on cloud-core and accessible by the container or host
        output = subprocess.check_output(["keadm", "gettoken", "--kube-config=/etc/rancher/k3s/k3s.yaml"], text=True)
        return jsonify({'token': output.strip()})
    except subprocess.CalledProcessError as e:
        logger.error("keadm error: " + str(e))
        return jsonify({'error': 'keadm failed', 'details': str(e)}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# small util endpoint to run a simple kubectl-like exec (NOT shell) - optional for troubleshooting
@app.route('/api/k8s/describe/pod', methods=['GET'])
def api_k8s_describe_pod():
    if not k8s:
        return jsonify({'error': 'Kubernetes client not available'}), 500
    namespace = request.args.get('namespace', 'default')
    pod = request.args.get('pod')
    if not pod:
        return jsonify({'error': 'pod parameter required'}), 400
    try:
        p = k8s.read_namespaced_pod(name=pod, namespace=namespace)
        # return selective describe-like info
        info = {
            'name': p.metadata.name,
            'namespace': p.metadata.namespace,
            'node': p.spec.node_name,
            'phase': p.status.phase,
            'conditions': [ {'type': c.type, 'status': c.status, 'lastTransition': c.last_transition_time} for c in (p.status.conditions or []) ],
            'containers': [ {'name': c.name, 'image': c.image} for c in (p.spec.containers or []) ],
            'startTime': p.status.start_time.isoformat() if p.status.start_time else None
        }
        return jsonify(info)
    except ApiException as e:
        return jsonify({'error': str(e)}), 500

# Start app
if __name__ == '__main__':
    logger.info("Starting Master App (Cloud) with Kubernetes support")
    # in production you will run this inside a WSGI; debug True is okay for local testing
    app.run(host='0.0.0.0', port=5000, debug=True)
