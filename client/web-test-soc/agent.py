from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import subprocess

app = FastAPI()

class IPPayload(BaseModel):
    ip: str

@app.post("/agent/ban")
def ban_ip(payload: IPPayload):
    ip = payload.ip
    # Đã điền IP thật để hệ thống không tự sát
    if ip in ["139.59.242.70", "143.198.82.147", "127.0.0.1"]:
        return {"status": "ignored", "message": "Không được phép khóa IP hệ thống"}

    try:
        # Kiểm tra xem IP đã bị khóa chưa
        check_cmd = f"iptables -C INPUT -s {ip} -j DROP"
        result = subprocess.run(check_cmd, shell=True, capture_output=True)
        if result.returncode == 0:
            return {"status": "success", "message": f"IP {ip} đã bị khóa từ trước."}

        # Thực thi lệnh khóa IP
        cmd = f"iptables -I INPUT -s {ip} -j DROP"
        subprocess.run(cmd, shell=True, check=True)
        print(f"[+] Đã chặn IP: {ip}")
        return {"status": "success", "message": f"Đã khóa IP {ip} trên server thành công!"}
    except subprocess.CalledProcessError as e:
        print(f"[-] Lỗi khi chặn IP {ip}: {e}")
        raise HTTPException(status_code=500, detail="Lỗi khi thực thi iptables")

@app.post("/agent/unban")
def unban_ip(payload: IPPayload):
    ip = payload.ip
    try:
        # Thực thi lệnh mở khóa IP
        cmd = f"iptables -D INPUT -s {ip} -j DROP"
        subprocess.run(cmd, shell=True, check=True)
        print(f"[+] Đã mở khóa IP: {ip}")
        return {"status": "success", "message": f"Đã mở khóa IP {ip} trên server thành công!"}
    except subprocess.CalledProcessError:
        return {"status": "success", "message": f"IP {ip} chưa bị khóa."}