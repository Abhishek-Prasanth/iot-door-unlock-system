# Neuralock 🔐📱

A secure AI-powered door lock system using **3D facial recognition**, **depth spoof detection**, and a **Flutter-based mobile app** for real-time admin control and logging.

This full-stack project integrates:
- Python-based face recognition and spoof protection on a **Raspberry Pi**
- An IoT-controlled **solenoid lock**
- A **Flutter app** for digital peephole, adding new users, and monitoring access attempts

---

## 🧠 Features

- Real-time 3D face unlock using DeepFace
- Depth map generation using a dot projector
- Spoof protection via IR + dot pattern analysis
- Local user face database and image logging
- PIN-based keypad fallback system
- Flutter mobile app:
  - View intruder logs
  - Add/update user profiles
  - Change PIN remotely (secure admin only)
  - See real-time video