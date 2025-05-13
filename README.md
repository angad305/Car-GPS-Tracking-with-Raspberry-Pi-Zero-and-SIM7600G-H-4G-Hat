# 🚗 Car-GPS-Tracking-with-Raspberry-Pi-Zero-and-SIM7600G-H-4G-Hat
Car GPS Tracking with Raspberry Pi Zero + SIM7600G-H 4G Hat + OLED + Traccar + Telegram

This project is a  GPS tracking system built using a Raspberry Pi and a SIM7600 modem. It connects to the internet via LTE, reads GPS data via AT commands, displays status on an OLED screen, and sends live location updates to a [Traccar](https://www.traccar.org/) server. It also sends a Telegram notification when the vehicle starts.

---

## ✨ Features

* Start LTE internet using PPP
* Get GPS coordinates using AT commands
* Push location data to Traccar every few seconds
* Display network & GPS status on 128x32 OLED
* Send Telegram notification when the car starts
* Systemd service to auto-start tracker on boot

---

## 🧰 Requirements

### ✅ Hardware:

* Raspberry Pi Zero 2W
* SIM7600G-H 4G HAT (sim card and GPS support)
* 0.91 inch OLED - 128×32 (I2C)

### ✅ Software:

```bash
sudo apt update
sudo apt install ppp python3-pip git -y
pip3 install Adafruit_SSD1306 Pillow requests pytz
```

---

## 📁 File Overview

| File                                      | Purpose                              |
| ----------------------------------------- | ------------------------------------ |
| `car.py`                                  | Main GPS + LTE tracker script        |
| `/usr/local/bin/start-lte`                | Bash script to initiate PPP over LTE |
| `/etc/chatscripts/sim7600g`               | Chatscript for dialing modem         |
| `/etc/ppp/peers/sim7600g`                 | PPP peer configuration for SIM7600   |
| `/etc/systemd/system/car-tracker.service` | Systemd service to auto-start script |

---

## ⚙️ Setup Instructions

### 🔌 1. Create Chatscript

PLEASE replace "www" with your apn (for your sim)

```bash
sudo nano /etc/chatscripts/sim7600g
```

Paste:

```text
ABORT "BUSY"
ABORT "NO CARRIER"
ABORT "NO DIALTONE"
ABORT "ERROR"
ABORT "NO ANSWER"
TIMEOUT 30
"" AT
OK ATE0
OK ATI;+CSUB;+CSQ;+CPIN?;+COPS?;+CGREG?;&D2
OK AT+CGDCONT=1,"IP","www"
OK ATD*99#
CONNECT ""
```

### 🔧 2. Configure PPP Peer

```bash
sudo nano /etc/ppp/peers/sim7600g
```

Paste:

```text
/dev/ttyUSB3
115200
connect "/usr/sbin/chat -v -f /etc/chatscripts/sim7600g"
noauth
defaultroute
usepeerdns
noipdefault
novj
novjccomp
noccp
ipcp-accept-local
ipcp-accept-remote
local
lock
crtscts
persist
holdoff 10
maxfail 0
defaultroute
replacedefaultroute
```

> ⚠️ Note: Use `dmesg | grep ttyUSB` to confirm the correct USB port (e.g., `ttyUSB3`).

### 🚀 3. Create LTE Start Script

```bash
sudo nano /usr/local/bin/start-lte
sudo chmod +x /usr/local/bin/start-lte
```

Paste script:

```bash
#!/bin/bash

echo "Starting LTE connection..."

# Kill any existing pppd processes
sudo killall pppd

# Start the PPP connection
sudo pon sim7600g

# Wait for ppp0 interface to come up (timeout after 30 seconds)
counter=0
while [ $counter -lt 30 ] && ! ip link show ppp0 >/dev/null 2>&1; do
    sleep 1
    ((counter++))
done

if ip link show ppp0 >/dev/null 2>&1; then
    echo "ppp0 interface is up"

    # Wait for the interface to get an IP address (timeout after 30 seconds)
    counter=0
    while [ $counter -lt 30 ] && ! ip addr show ppp0 | grep -q "inet "; do
        sleep 1
        ((counter++))
    done

    if ip addr show ppp0 | grep -q "inet "; then
        # Remove existing default route
        sudo ip route del default

        # Add new default route via ppp0
        sudo ip route add default dev ppp0

        echo "Default route added via ppp0"
        ip addr show ppp0
        ip route
        echo "LTE connection established successfully!"
    else
        echo "ppp0 interface did not receive an IP address."
        sudo poff sim7600g
        exit 1
    fi
else
    echo "Failed to establish LTE connection. ppp0 interface did not come up."
    exit 1
fi
```

### 📟 4. Enable OLED & Permissions

Ensure I2C is enabled:

```bash
sudo raspi-config  # Interfacing Options → I2C → Enable
```

Give permission to the `angad` user (or your username) to access serial and I2C:

```bash
sudo usermod -aG dialout,i2c angad
```

---

## 🔁 Auto-Start on Boot

### 🛠️ Create Systemd Service

```bash
sudo nano /etc/systemd/system/car-tracker.service
```

Paste:

```ini
[Unit]
Description=Car GPS Tracker Service
After=network.target

[Service]
ExecStartPre=/bin/sleep 10
ExecStart=/usr/bin/python3 /home/angad/car.py
Restart=always
User=angad
Group=angad
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable car-tracker.service
sudo systemctl start car-tracker.service
```

Check status:

```bash
sudo systemctl status car-tracker.service
```

---

## ✉️ Telegram Alerts

The script will send a notification like `"Car Started..."` via Telegram.
You must set these in the script:

```python
TOKEN = '[YOUR TELEGRAM BOT TOKEN]'
chat_id = '[YOUR CHAT ID]'
```

Use [@BotFather](https://t.me/BotFather) to create a bot, and [get chat ID](https://t.me/userinfobot).

---

## 🌍 Traccar Server Integration

Set your server URL in the script:

```python
TRACCAR_URL = "http://<your-server-ip>:5055/"
```

This sends data in the format Traccar expects:

* `lat`, `lon`, `timestamp`, `speed`, etc.

---

## 📌 Customize

Edit these values in `car.py` for your needs:

```python
SEND_POSTN_EVERY = 3  # Seconds between GPS updates
DEVICE_ID = '1baleno' # Traccar device ID
```

---

## 🛠️ Troubleshooting

* Use `dmesg | grep ttyUSB` to find modem ports
* Use `sudo poff sim7600g` to manually stop PPP
* Check logs: `journalctl -u car-tracker.service -f`
* If OLED is blank: ensure I2C is enabled and fonts installed

---

## 📜 License

MIT License

---

## ❤️ Credits

By Angad Cheema
Inspired by real-world car tracking needs with GSM/LTE support.

---

