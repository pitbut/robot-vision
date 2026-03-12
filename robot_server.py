# -*- coding: utf-8 -*-
# robot_server.py - glavny server na Render.com
from flask import Flask, request, jsonify, render_template_string
import anthropic, os, json, base64

app = Flask(__name__)

API_KEY = {"value": os.environ.get("ANTHROPIC_API_KEY", "")}

DEFAULT_PROMPT = """You are the brain of a robot with two arms.
You look at a camera image and decide what the robot should do.

Available motions:
- wave  : wave right hand (person greets or waves)
- grab  : extend both arms forward (person offers object)
- point : extend right arm to side (person points somewhere)
- nod   : both arms slightly down then up (person nods yes)
- push  : both arms forward then back (person pushes gesture)
- idle  : both arms relaxed at sides (nothing happening)

Respond ONLY with valid JSON:
{"motion":"idle","reason":"describe what you see in Russian","confidence":0.9}"""

PROMPT = {"value": DEFAULT_PROMPT}

# ------- ROUTES -------

@app.route("/")
def index():
    return render_template_string(PAGE)

@app.route("/set_key", methods=["POST"])
def set_key():
    k = request.json.get("key", "").strip()
    if k.startswith("sk-ant"):
        API_KEY["value"] = k
        return jsonify({"ok": True})
    return jsonify({"error": "Wrong key format"}), 400

@app.route("/get_prompt", methods=["GET"])
def get_prompt():
    return jsonify({"prompt": PROMPT["value"]})

@app.route("/set_prompt", methods=["POST"])
def set_prompt():
    p = request.json.get("prompt", "").strip()
    if p:
        PROMPT["value"] = p
        return jsonify({"ok": True})
    return jsonify({"error": "Empty prompt"}), 400

# ESP32-CAM calls this endpoint with image
@app.route("/cam", methods=["POST"])
def cam():
    """
    ESP32-CAM sends: {"image": "base64_jpeg_data"}
    Server returns:  {"motion": "wave", "reason": "..."}
    """
    if not API_KEY["value"]:
        return jsonify({"motion": "idle", "error": "No API key"}), 400

    data = request.json
    if not data or "image" not in data:
        return jsonify({"motion": "idle", "error": "No image"}), 400

    b64 = data["image"]

    try:
        client = anthropic.Anthropic(api_key=API_KEY["value"])
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=200,
            system=PROMPT["value"],
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": b64
                        }
                    },
                    {
                        "type": "text",
                        "text": "What gesture? JSON only."
                    }
                ]
            }]
        )
        raw = resp.content[0].text.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)
        print(f"Motion: {result.get('motion')} | {result.get('reason', '')}")
        return jsonify(result)

    except json.JSONDecodeError:
        return jsonify({"motion": "idle", "reason": raw})
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"motion": "idle", "error": str(e)}), 500


# ESP32 Master polls this to get latest command
LATEST_MOTION = {"value": "idle"}

@app.route("/motion", methods=["GET"])
def get_motion():
    """ESP32 Master polls this every second to get command"""
    return jsonify({"motion": LATEST_MOTION["value"]})

@app.route("/motion", methods=["POST"])
def set_motion_internal():
    """Internal: update latest motion after cam analysis"""
    m = request.json.get("motion", "idle")
    LATEST_MOTION["value"] = m
    return jsonify({"ok": True})


# Web UI calls analyze
@app.route("/analyze", methods=["POST"])
def analyze():
    b64 = request.json.get("image", "")
    if not b64:
        return jsonify({"error": "No image"}), 400

    if not API_KEY["value"]:
        return jsonify({"error": "Enter API key first"}), 400

    try:
        client = anthropic.Anthropic(api_key=API_KEY["value"])
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=200,
            system=PROMPT["value"],
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": "What gesture? JSON only."}
                ]
            }]
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        result = json.loads(raw)
        LATEST_MOTION["value"] = result.get("motion", "idle")
        return jsonify(result)
    except json.JSONDecodeError:
        return jsonify({"motion": "idle", "reason": raw})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robot Vision</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#030712;color:#e2e8f0;font-family:'Courier New',monospace;
     min-height:100vh;display:flex;flex-direction:column;align-items:center;padding:16px;gap:12px}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
@keyframes waveIt{from{transform:rotate(-50deg)}to{transform:rotate(-10deg)}}
h1{font-size:20px;font-weight:900;letter-spacing:3px;transition:color .5s}
.sub{font-size:9px;letter-spacing:4px;color:#374151}
.panel{background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:14px;width:100%;max-width:740px}
.ptitle{font-size:9px;letter-spacing:3px;color:#374151;margin-bottom:10px}
.row{display:flex;gap:12px;flex-wrap:wrap;justify-content:center;width:100%;max-width:740px}
#cam-wrap{position:relative;border-radius:8px;overflow:hidden;background:#000;aspect-ratio:4/3;width:100%}
#video{width:100%;height:100%;object-fit:cover;display:block}
#ov{position:absolute;inset:0;background:#00000088;display:none;align-items:center;justify-content:center}
.sp{width:32px;height:32px;border:3px solid #ffffff22;border-top-color:#00ff88;border-radius:50%;animation:spin .8s linear infinite}
#livebadge{position:absolute;top:6px;left:6px;background:#00000099;border-radius:4px;
           padding:2px 6px;font-size:8px;color:#00ff88;display:none;align-items:center;gap:4px}
button{cursor:pointer;border:none;font-family:'Courier New',monospace;font-weight:bold;
       letter-spacing:1px;transition:all .2s;border-radius:6px;font-size:10px;padding:9px 12px}
button:hover:not(:disabled){transform:translateY(-2px);filter:brightness(1.2)}
button:disabled{opacity:.4;cursor:not-allowed}
.bg{background:#00ff8822;border:1px solid #00ff88;color:#00ff88}
.br{background:#ff6b3522;border:1px solid #ff6b35;color:#ff6b35}
.bgr{background:#1e293b;border:1px solid #374151;color:#6b7280}
#bstart{flex:1} #banalyze{flex:2;display:none} #bauto{flex:1;display:none}
#automsg{font-size:8px;color:#ff6b35;text-align:center;margin-top:5px;display:none;animation:pulse 1.5s infinite}
#rpanel{flex:1 1 160px;max-width:190px;display:flex;flex-direction:column;align-items:center;transition:border-color .5s}
#mlabel{font-size:15px;font-weight:900;letter-spacing:3px;transition:color .5s;margin-top:6px}
#mdesc{font-size:9px;color:#6b7280;margin-top:2px;text-align:center}
#mcmd{font-size:8px;color:#1f2937;margin-top:4px;letter-spacing:1px}
#vbox{font-size:11px;color:#94a3b8;line-height:1.8;min-height:36px}
#loglist{display:flex;flex-direction:column;gap:3px;min-height:36px}
.le{display:flex;gap:8px;font-size:9px}
.lt{color:#374151;flex-shrink:0}
.lok{color:#00ff88}.lerr{color:#ff4444}.linfo{color:#6b7280}
.mb{padding:5px 10px;border-radius:6px;border:1px solid #1e293b;background:transparent;color:#4b5563;font-size:9px;cursor:pointer;transition:all .2s}
#cpanel{flex:1 1 260px;max-width:340px}
canvas{display:none}
input[type=password],input[type=text]{
  background:#030712;border:1px solid #374151;color:#e2e8f0;
  font-family:'Courier New',monospace;font-size:10px;padding:9px 11px;border-radius:6px;outline:none;width:100%}
textarea{width:100%;background:#030712;border:1px solid #1e293b;color:#94a3b8;
  font-family:'Courier New',monospace;font-size:10px;padding:11px;border-radius:8px;
  outline:none;resize:vertical;line-height:1.7}
textarea:focus{border-color:#475569}
.tag{display:inline-block;padding:2px 9px;border-radius:20px;font-size:9px;
     border:1px solid #1e293b;color:#6b7280;cursor:pointer;transition:all .2s;margin:2px}
.tag:hover{border-color:#00ff88;color:#00ff88}
.tag.on{border-color:#00ff88;background:#00ff8822;color:#00ff88}
#urlbox{background:#030712;border:1px solid #1e293b;border-radius:6px;padding:10px;
        font-size:10px;color:#00ff88;word-break:break-all;margin-top:6px}
</style>
</head>
<body>

<div style="text-align:center">
  <div class="sub">ROBOT CONTROL SYSTEM v2</div>
  <h1 id="mtitle" style="color:#475569">ROBOT VISION</h1>
  <div class="sub" style="margin-top:3px">ESP32 + CLAUDE + RENDER.COM</div>
</div>

<!-- SERVER URL INFO -->
<div class="panel">
  <div class="ptitle">SERVER ENDPOINTS (for ESP32 code)</div>
  <div id="urlbox">Loading server URL...</div>
</div>

<!-- API KEY -->
<div class="panel">
  <div class="ptitle">ANTHROPIC API KEY</div>
  <div style="display:flex;gap:8px">
    <input id="apikey" type="password" placeholder="sk-ant-api03-...">
    <button class="bg" onclick="saveKey()" style="white-space:nowrap">SAVE</button>
    <button class="bgr" onclick="toggleV()" style="white-space:nowrap">SHOW</button>
  </div>
  <div id="kmsg" style="font-size:9px;color:#374151;margin-top:5px">
    Paste key from console.anthropic.com
  </div>
</div>

<!-- PROMPT EDITOR -->
<div class="panel">
  <div class="ptitle">ROBOT BEHAVIOR (edit and save)</div>
  <div style="margin-bottom:8px">
    <span class="tag on" onclick="loadT('default')">Default</span>
    <span class="tag" onclick="loadT('guard')">Guard</span>
    <span class="tag" onclick="loadT('greet')">Greeting</span>
    <span class="tag" onclick="loadT('helper')">Helper</span>
  </div>
  <textarea id="pe" rows="10"></textarea>
  <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
    <button class="bg" onclick="savePrompt()">SAVE BEHAVIOR</button>
    <button class="bgr" onclick="loadPrompt()">RESET</button>
    <div id="pmsg" style="font-size:9px;color:#374151;margin-left:6px"></div>
  </div>
</div>

<!-- CAMERA + ROBOT -->
<div class="row">
  <div class="panel" id="cpanel">
    <div class="ptitle">WEBCAM (test from browser)</div>
    <div id="cam-wrap">
      <video id="video" muted playsinline></video>
      <div id="ov"><div class="sp"></div></div>
      <div id="livebadge">
        <span style="width:5px;height:5px;border-radius:50%;background:#00ff88;animation:pulse 1s infinite;display:inline-block"></span>LIVE
      </div>
    </div>
    <canvas id="canvas"></canvas>
    <div style="display:flex;gap:8px;margin-top:9px">
      <button id="bstart"   class="bg" onclick="startCam()">START CAM</button>
      <button id="banalyze" class="bg" onclick="analyze()">ANALYZE</button>
      <button id="bauto"    class="bgr" onclick="toggleAuto()">AUTO</button>
    </div>
    <div id="automsg">AUTO EVERY 3 SEC</div>
  </div>

  <div class="panel" id="rpanel">
    <div class="ptitle" style="align-self:flex-start">ROBOT STATUS</div>
    <svg viewBox="0 0 120 185" width="90" height="148">
      <rect x="42" y="138" width="14" height="32" rx="6" fill="#1e293b" stroke="#475569" stroke-width="1"/>
      <rect x="64" y="138" width="14" height="32" rx="6" fill="#1e293b" stroke="#475569" stroke-width="1"/>
      <rect id="br" x="33" y="78" width="54" height="62" rx="9" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
      <circle id="bc" cx="60" cy="109" r="11" fill="none" stroke="#475569" stroke-width="1" opacity=".4"/>
      <circle id="bd" cx="60" cy="109" r="5" fill="#475569" opacity=".6"/>
      <rect x="51" y="73" width="18" height="7" rx="3" fill="#1e293b" stroke="#475569" stroke-width="1" opacity=".6"/>
      <rect id="hdr" x="30" y="25" width="60" height="50" rx="11" fill="#1e293b" stroke="#475569" stroke-width="2"/>
      <ellipse id="el" cx="46" cy="48" rx="6" ry="6" fill="#475569"/>
      <ellipse id="er" cx="74" cy="48" rx="6" ry="6" fill="#475569"/>
      <rect id="mo" x="45" y="62" width="30" height="4" rx="2" fill="#475569" opacity=".3"/>
      <g id="al" style="transform-origin:26px 86px;transition:transform .5s cubic-bezier(.34,1.56,.64,1)">
        <rect x="15" y="78" width="14" height="48" rx="7" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
      </g>
      <g id="ar" style="transform-origin:94px 86px;transition:transform .5s cubic-bezier(.34,1.56,.64,1)">
        <rect x="91" y="78" width="14" height="48" rx="7" fill="#1e293b" stroke="#475569" stroke-width="1.5"/>
      </g>
    </svg>
    <div id="mlabel">IDLE</div>
    <div id="mdesc">Waiting</div>
    <div id="mcmd">cmd: idle</div>
    <div style="margin-top:10px;display:flex;gap:4px;flex-wrap:wrap;justify-content:center">
      <button class="mb" onclick="setM('wave')">WAVE</button>
      <button class="mb" onclick="setM('grab')">GRAB</button>
      <button class="mb" onclick="setM('point')">POINT</button>
      <button class="mb" onclick="setM('nod')">NOD</button>
      <button class="mb" onclick="setM('push')">PUSH</button>
      <button class="mb" onclick="setM('idle')">IDLE</button>
    </div>
  </div>
</div>

<!-- CLAUDE SEES -->
<div class="panel">
  <div class="ptitle">CLAUDE SEES</div>
  <div id="vbox">Start camera and click ANALYZE...</div>
</div>

<!-- LOG -->
<div class="panel">
  <div class="ptitle">LOG</div>
  <div id="loglist"><div class="le"><span class="linfo">Ready.</span></div></div>
</div>

<script>
var MP={
  wave: {desc:"Greeting",  color:"#00ff88",la:20, ra:-55},
  grab: {desc:"Grab",      color:"#ff6b35",la:-25,ra:25 },
  point:{desc:"Point",     color:"#4ecdc4",la:30, ra:-70},
  nod:  {desc:"Agree",     color:"#a78bfa",la:10, ra:-10},
  push: {desc:"Push away", color:"#f59e0b",la:-35,ra:35 },
  idle: {desc:"Waiting",   color:"#475569",la:30, ra:-30}
};
var TEMPLATES={
  default:"You are the brain of a robot with two arms.\\nYou look at a camera image and decide what the robot should do.\\n\\nAvailable motions:\\n- wave  : wave right hand (person greets or waves)\\n- grab  : extend both arms forward (person offers object)\\n- point : extend right arm to side (person points somewhere)\\n- nod   : both arms slightly down then up (person nods yes)\\n- push  : both arms forward then back (person pushes gesture)\\n- idle  : both arms relaxed at sides (nothing happening)\\n\\nRespond ONLY with valid JSON:\\n{\\\"motion\\\":\\\"idle\\\",\\\"reason\\\":\\\"describe what you see in Russian\\\",\\\"confidence\\\":0.9}",
  greet:"You are a friendly greeting robot.\\nWave when someone enters or waves at you.\\nNod when they smile or agree.\\nStand idle when nobody interacts.\\n\\nAvailable motions: wave, nod, idle\\n\\nRespond ONLY with JSON: {\\\"motion\\\":\\\"idle\\\",\\\"reason\\\":\\\"what you see in Russian\\\"}",
  guard:"You are a security guard robot.\\nPoint when you see something suspicious.\\nPush when someone gets too close.\\nWave for authorized persons.\\nStand idle when everything is normal.\\n\\nAvailable motions: wave, point, push, idle\\n\\nRespond ONLY with JSON: {\\\"motion\\\":\\\"idle\\\",\\\"reason\\\":\\\"what you see in Russian\\\"}",
  helper:"You are a helpful assistant robot.\\nGrab when person offers something.\\nPoint when person points somewhere.\\nWave to get attention.\\nNod to confirm.\\nPush to signal stop.\\n\\nAvailable motions: wave, grab, point, nod, push, idle\\n\\nRespond ONLY with JSON: {\\\"motion\\\":\\\"idle\\\",\\\"reason\\\":\\\"what you see in Russian\\\"}"
};

var camOn=false,loading=false,autoMode=false,autoTimer=null;

// Show server URL for ESP32
window.onload=function(){
  var url=window.location.origin;
  document.getElementById("urlbox").innerHTML=
    "<b>CAM endpoint:</b> "+url+"/cam<br>"+
    "<b>Motion poll:</b> "+url+"/motion<br>"+
    "<b>Web UI:</b> "+url+"/";
  loadPrompt();
};

async function saveKey(){
  var k=document.getElementById("apikey").value.trim();
  var msg=document.getElementById("kmsg");
  if(!k.startsWith("sk-ant")){msg.textContent="Key must start with sk-ant-...";msg.style.color="#f59e0b";return;}
  var r=await fetch("/set_key",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key:k})});
  var d=await r.json();
  if(d.ok){msg.textContent="Key saved!";msg.style.color="#00ff88";}
  else{msg.textContent="Error: "+d.error;msg.style.color="#ff4444";}
}
function toggleV(){var i=document.getElementById("apikey");i.type=i.type==="password"?"text":"password";}

function loadT(name){document.getElementById("pe").value=TEMPLATES[name]||"";}

async function loadPrompt(){
  var r=await fetch("/get_prompt");
  var d=await r.json();
  document.getElementById("pe").value=d.prompt;
}
async function savePrompt(){
  var p=document.getElementById("pe").value.trim();
  var msg=document.getElementById("pmsg");
  if(!p){msg.textContent="Empty!";msg.style.color="#ff4444";return;}
  var r=await fetch("/set_prompt",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({prompt:p})});
  var d=await r.json();
  if(d.ok){msg.textContent="Saved!";msg.style.color="#00ff88";setTimeout(function(){msg.textContent="";},2000);}
}

function setM(name){
  var m=MP[name]||MP.idle;
  document.getElementById("al").style.transform="rotate("+m.la+"deg)";
  document.getElementById("ar").style.transform="rotate("+m.ra+"deg)";
  document.getElementById("ar").style.animation=name==="wave"?"waveIt .6s ease-in-out infinite alternate":"none";
  ["br","hdr"].forEach(function(id){document.getElementById(id).setAttribute("stroke",m.color);});
  ["bc","bd","el","er","mo"].forEach(function(id){document.getElementById(id).setAttribute("fill",m.color);});
  document.getElementById("mtitle").style.color=m.color;
  document.getElementById("rpanel").style.borderColor=m.color+"55";
  document.getElementById("mlabel").textContent=name.toUpperCase();
  document.getElementById("mlabel").style.color=m.color;
  document.getElementById("mdesc").textContent=m.desc;
  document.getElementById("mcmd").textContent="cmd: "+name;
  document.querySelectorAll(".mb").forEach(function(b){
    var a=b.textContent.toLowerCase()===name;
    b.style.borderColor=a?m.color:"#1e293b";
    b.style.background=a?m.color+"22":"transparent";
    b.style.color=a?m.color:"#4b5563";
  });
}

function addLog(txt,type){
  var d=document.createElement("div");d.className="le";
  d.innerHTML="<span class='lt'>"+new Date().toLocaleTimeString()+"</span><span class='l"+type+"'>"+txt+"</span>";
  var l=document.getElementById("loglist");
  l.insertBefore(d,l.firstChild);
  while(l.children.length>15)l.removeChild(l.lastChild);
}

async function startCam(){
  try{
    var s=await navigator.mediaDevices.getUserMedia({video:{width:640,height:480}});
    document.getElementById("video").srcObject=s;
    await document.getElementById("video").play();
    camOn=true;
    document.getElementById("livebadge").style.display="flex";
    document.getElementById("bstart").style.display="none";
    document.getElementById("banalyze").style.display="flex";
    document.getElementById("bauto").style.display="flex";
    addLog("Camera started","ok");
  }catch(e){addLog("Camera error: "+e.message,"err");}
}

async function analyze(){
  if(!camOn||loading)return;
  var vd=document.getElementById("video");
  var cv=document.getElementById("canvas");
  cv.width=vd.videoWidth||640;cv.height=vd.videoHeight||480;
  cv.getContext("2d").drawImage(vd,0,0,cv.width,cv.height);
  var b64=cv.toDataURL("image/jpeg",0.8).split(",")[1];
  loading=true;
  document.getElementById("ov").style.display="flex";
  document.getElementById("banalyze").disabled=true;
  addLog("Sending to Claude...","info");
  try{
    var res=await fetch("/analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({image:b64})});
    var data=await res.json();
    if(data.error){
      addLog("Error: "+data.error,"err");
      document.getElementById("vbox").textContent="Error: "+data.error;
    }else{
      setM(data.motion||"idle");
      document.getElementById("vbox").textContent=data.reason||"no description";
      addLog((data.motion||"idle").toUpperCase()+" | "+(data.reason||""),"ok");
    }
  }catch(e){addLog("Error: "+e.message,"err");}
  loading=false;
  document.getElementById("ov").style.display="none";
  document.getElementById("banalyze").disabled=false;
}

function toggleAuto(){
  autoMode=!autoMode;
  var b=document.getElementById("bauto"),m=document.getElementById("automsg");
  if(autoMode){
    b.textContent="STOP";b.style.background="#ff6b3522";b.style.borderColor="#ff6b35";b.style.color="#ff6b35";
    m.style.display="block";autoTimer=setInterval(analyze,3000);
    addLog("Auto mode ON","ok");
  }else{
    b.textContent="AUTO";b.style.background="#1e293b";b.style.borderColor="#374151";b.style.color="#6b7280";
    m.style.display="none";clearInterval(autoTimer);
    addLog("Auto mode OFF","info");
  }
}
setM("idle");
</script>
</body>
</html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("ROBOT SERVER started on port", port)
    app.run(host="0.0.0.0", port=port, debug=False)
