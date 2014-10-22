import os, time, io, smtplib, types, picamera
import MailWrapper
from datetime import datetime
from PIL import Image
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email import Encoders

class Argus(object):
    def __init__(self, root_dir, email_creds):
        self.alert_active = False
        self.root_dir = root_dir
        self.email_username, self.email_password = email_creds
        self.current_image = None
        self.current_pil_buffer = None
        self.video_stream = None
        self.camera = None
        self.motion_detected = None
        self.last_motion = None
        self.current_file_path = None

    def Start(self):
        self.initEmail()
        self.init_camera()
        time.sleep(2)
        self.initVideoStream()
        time.sleep(2)
        self.initImage()
        time.sleep(5)
        while True:
            time.sleep(2)
            self.checkForMotion()

    def initEmail(self):
        self.email_manager = MailWrapper.MailWrapper(self.email_username, self.email_password)
        self.email_manager.addReceiver('jenningstm117@gmail.com')

        self.alert_active_subject = 'Argus Alert Activated'
        self.alert_deactive_subject = 'Argus Alert Deactivated'


    def init_camera(self):
        self.camera = picamera.PiCamera()
        self.camera.resolution = (100, 75)

    def initImage(self):
        self.current_image, self.current_pil_buffer = self.captureImage()

    def captureImage(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg', use_video_port=True)
        # "Rewind" the stream to the beginning so we can read its content
        stream.seek(0)
        image = Image.open(stream)
        buffer = image.load()
        stream.close()
        return image, buffer

    def initVideoStream(self):
        self.video_stream = picamera.PiCameraCircularIO(self.camera, seconds=5)
        self.camera.start_recording(self.video_stream, format='h264')

    def recordVideoToFile(self, file_name):
        self.camera.start_recording(file_name)

    def stopVideoRecording(self):
        self.camera.stop_recording()

    def persistVideo(self, newFilename, tempFilename):
        for frame in self.video_stream.frames:
            if frame.header:
                self.video_stream.seek(frame.position)
                break
        with open(tempFilename, 'rb') as tempFile, open(newFilename, 'wb') as newFile:
            while True:
                data = self.video_stream.read1()
                if not data:
                    break
                newFile.write(data)
            for chunk in iter(lambda: tempFile.read(1024), b""):
                newFile.write(chunk)
        os.remove(tempFilename)


    def checkForMotion(self):
        motion_detected = False
        new_image, new_buffer = self.captureImage()
        changedPixels = 0
        for x in xrange(0, 100):
            for y in xrange(0, 75):
                # Just check green channel as it's the highest quality channel
                pixdiff = abs(self.current_pil_buffer[x,y][1] - new_buffer[x,y][1])
                if pixdiff > 10:
                    changedPixels += 1

        if changedPixels > 20:
            motion_detected = True
            self.last_motion = int(time.time())
        self.current_image, self.current_pil_buffer = new_image, new_buffer

        if motion_detected and not self.alert_active:
            self.activateAlert()
        elif not motion_detected and self.alert_active and int(time.time())-self.last_motion>60:
            self.deactivateAlert()

    def activateAlert(self):
        self.alert_active = True
        self.current_file_path = self.getFilePath()
        self.saveCurrentImage('%s%s'%(self.current_file_path, self.getFilename('alertActivated')))
        self.sendAlertEmail('alertActivated', '%s%s'%(self.current_file_path, self.getFilename('alertActivated')))
        self.stopVideoRecording()
        self.recordVideoToFile('%s%s'%(self.current_file_path, 'temp.h264'))


    def deactivateAlert(self):
        self.alert_active = False
        self.saveCurrentImage('%s%s'%(self.current_file_path, self.getFilename('alertDeactivated')))
        self.sendAlertEmail('alertDeactivated', '%s%s'%(self.current_file_path, self.getFilename('alertDeactivated')))
        self.stopVideoRecording()
        self.persistVideo('%s%s'%(self.current_file_path, self.getFilename('video')), '%stemp.h264'%self.current_file_path)
        self.initVideoStream()
        self.initImage()

    def sendAlertEmail(self, type, image_file):
        if type == 'alertActivated':
            self.email_manager.createMail(self.alert_active_subject, '')
            self.email_manager.attachFile(image_file)
            self.email_manager.sendMail()
        elif type == 'alertDeactivated':
            self.email_manager.createMail(self.alert_deactive_subject, '')
            self.email_manager.attachFile(image_file)
            self.email_manager.sendMail()

    def saveCurrentImage(self, filename):
        self.current_image.save(filename)

    def getFilePath(self):
        now = datetime.now()
        year = now.year
        month = now.month
        day = now.day
        hour = now.hour
        minute=now.minute
        filePath = '%s/%s/%s/%s/%02d%02d/'%(self.root_dir, year, month, day, hour, minute)
        if not os.path.exists(filePath):
            os.makedirs(filePath)
        return filePath

    def getFilename(self, fileType):
        if fileType=='alertActivated':
            return 'alertActivated.jpeg'
        elif fileType=='alertDeactivated':
            return 'alertDeactivated.jpeg'
        elif fileType=='video':
            return 'video.h264'