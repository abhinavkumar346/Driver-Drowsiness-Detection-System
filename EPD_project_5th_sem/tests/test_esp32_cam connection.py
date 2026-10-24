import cv2

url = "http://172.20.10.4:81/stream"
cap = cv2.VideoCapture(url)

while True:
    ok, frame = cap.read()
    if not ok:
        print("Failed to grab frame")
        break

    cv2.imshow("ESP32-CAM", frame)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()