import os, time, io, picamera, subprocess, alsaaudio, thread, wave
import numpy
import RPi.GPIO as GPIO
import MailWrapper
from datetime import datetime
from dateutil import tz
from PIL import Image


class ArgusPIR(object):
    def __init__(self, root_dir, email_creds):
        self.alert_active = False
        self.root_dir = root_dir
        self.email_username, self.email_password = email_creds
        self.PIR_PIN = None
        self.video_stream = None
        self.camera = None
        self.motion_detected = None
        self.last_motion = None
        self.current_file_path = None

    def Start(self):
        print 'starting'
        self.initEmail()
        self.init_camera()
        time.sleep(2)
        self.initVideoStream()
        time.sleep(5)
        self.initPirModule()
        time.sleep(3)
        checkedin = False
        ## Sit in a loop checking for motion every couple seconds
        try:
            while 1:
                now = self.getLocalDatetime()
                if now.hour == 12 and not checkedin:
                    checkedin = True
                    self.sendAlertEmail('checkin', None)
                elif now.hour == 13:
                    checkedin = False
                time.sleep(15)
                if self.alert_active and int(time.time())-self.last_motion>=30:
                    self.deactivateAlert()
        except KeyboardInterrupt:
            print 'Exiting . . .'
            GPIO.cleanup()

    ## Setup email notifications
    def initEmail(self):
        self.email_manager = MailWrapper.MailWrapper(self.email_username, self.email_password)
        self.email_manager.addReceiver('jenningstm117@gmail.com')

        self.alert_active_subject = 'Argus Alert Activated'
        self.alert_deactive_subject = 'Argus Alert Deactivated'
        self.alert_checkin_subject = 'Argus Checking In'

    ##Setup Pir motion detection device
    def initPirModule(self):
        GPIO.setmode(GPIO.BCM)
        self.PIR_PIN = 7
        GPIO.setup(self.PIR_PIN, GPIO.IN)

        time.sleep(2)
        GPIO.add_event_detect(self.PIR_PIN, GPIO.RISING, callback = self.motionDetected_callback)

    def motionDetected_callback(self, event):
        print 'motion_detected'
        self.motion_detected = True
        self.last_motion = time.time()

        if not self.alert_active:
            self.activateAlert()


    ## Create PiCamera Camera instance which Argus will use for recording any images/videos
    def init_camera(self):
        self.camera = picamera.PiCamera()
        self.camera.resolution = (1280, 720)

    ## Get initial image to use in comparisons for motion detection
    def initImage(self):
        self.current_image, self.current_pil_buffer = self.captureImage()

    ## Capture image and store in memory as an actual image as well as a buffer of pixel values using PIL.Image
    def captureImage(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg', use_video_port=True)
        # "Rewind" the stream to the beginning so we can read its content
        stream.seek(0)
        image = Image.open(stream)
        buffer = image.load()
        stream.close()
        return image

    ## Setup video recording to circular stream in memory, so the past 5 seconds of video will always be available
    def initVideoStream(self):
        self.video_stream = picamera.PiCameraCircularIO(self.camera, seconds=5)
        self.camera.start_recording(self.video_stream, format='h264')

    ## Record video to file . . . duh
    def recordVideoToFile(self, file_name):
        self.camera.start_recording(file_name)

    ## Stop recording video, so that recording to a different location can be done with the same PiCamera object
    def stopVideoRecording(self):
        self.camera.stop_recording()

    def copyStreamToFile(self):
        # Write the entire content of the circular buffer to disk. No need to
        # lock the stream here as we're definitely not writing to it
        # simultaneously
        with io.open(self.current_file_path+'before.h264', 'wb') as output:
            for frame in self.video_stream.frames:
                if frame.frame_type == picamera.PiVideoFrameType.sps_header:
                    self.video_stream.seek(frame.position)
                    break
            while True:
                buf = self.video_stream.read1()
                if not buf:
                    break
                output.write(buf)
        # Wipe the circular stream once we're done
        self.video_stream.seek(0)
        self.video_stream.truncate()

    ## take the 5 second video stream and combine it with a video file, into one new file
    def persistVideo(self):
        before = self.current_file_path+'before.h264'
        after = self.current_file_path+'after.h264'
        final = self.current_file_path+'video.h264'
        with open(before, 'rb') as beforeFile, open(after, 'rb') as afterFile, open(final, 'wb') as newFile:
            for chunk in iter(lambda: beforeFile.read(1024), b""):
                newFile.write(chunk)
            for chunk in iter(lambda: afterFile.read(1024), b""):
                newFile.write(chunk)
        os.remove(before)
        os.remove(after)

    def startAudioRecord(self, filename):
        inp = alsaaudio.PCM(alsaaudio.PCM_CAPTURE)
        inp.setchannels(1)
        inp.setrate(48000)
        inp.setformat(alsaaudio.PCM_FORMAT_S16_LE)
        inp.setperiodsize(1024)

        w = wave.open(filename, 'w')
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(48000)

        while True:
            l, data = inp.read()
            a = numpy.fromstring(data, dtype='int16')
            w.writeframes(data)

    ## When an alert is activated, get the file path based on current date and time, save the image
    ## that captured the motion, send the image in an email, stop recording to the circular stream, and
    ## start recording to a file
    def activateAlert(self):
        self.alert_active = True
        self.current_file_path = self.getFilePath()
        audio_filename = self.current_file_path + 'audio.wav'
        self.saveImage('%s%s'%(self.current_file_path, self.getFilename('alertActivated')))
        self.sendAlertEmail('alertActivated', '%s%s'%(self.current_file_path, self.getFilename('alertActivated')))
        self.camera.split_recording(self.current_file_path+'after.h264')
        thread.start_new_thread(self.startAudioRecord, (audio_filename,))
        self.copyStreamToFile()


    ## When an alert is deactivated, save the image, send it in an email, persist the final video file,
    ## and start watching for motion again
    def deactivateAlert(self):
        self.camera.split_recording(self.video_stream)
        self.saveImage('%s%s'%(self.current_file_path, self.getFilename('alertDeactivated')))
        self.sendAlertEmail('alertDeactivated', '%s%s'%(self.current_file_path, self.getFilename('alertDeactivated')))
        self.persistVideo()
        self.alert_active = False

    ## Construct the alert email to be sent
    def sendAlertEmail(self, type, image_file):
        try:
            if type == 'alertActivated':
                self.email_manager.createMail(self.alert_active_subject, '')
                self.email_manager.attachFile(image_file)
                self.email_manager.sendMail()
            elif type == 'alertDeactivated':
                self.email_manager.createMail(self.alert_deactive_subject, '')
                self.email_manager.attachFile(image_file)
                self.email_manager.sendMail()
            elif type == 'checkin':
                size, available = self.getFreeSpace()
                self.email_manager.createMail(self.alert_checkin_subject, '{0}Gb Free of {1}Gb Total'.format(available, size))
                self.email_manager.sendMail()
        except Exception as e:
            print 'sending failed'
            print e

    ## Save the current image in memory to a file
    def saveImage(self, filename):
        image = self.captureImage()
        image.save(filename)

    ## Get the file path based on current date and time
    def getFilePath(self):
        now = self.getLocalDatetime()
        year = now.year
        month = now.month
        day = now.day
        hour = now.hour
        minute=now.minute
        filePath = '%s/%s/%s/%s/%02d:%02d/'%(self.root_dir, year, month, day, hour, minute)
        if not os.path.exists(filePath):
            os.makedirs(filePath)
        return filePath

    ## Get filename based on alert status and media type
    def getFilename(self, fileType):
        if fileType=='alertActivated':
            return 'alertActivated.jpeg'
        elif fileType=='alertDeactivated':
            return 'alertDeactivated.jpeg'
        elif fileType=='video':
            return 'video.h264'

    def getFreeSpace(self):
        df = subprocess.Popen(["df", "/home/pi/ArgusAlertSystem/Main.py"], stdout=subprocess.PIPE)
        output = df.communicate()[0]
        device, size, used, available, percent, mountpoint = output.split("\n")[1].split()
        size = float(size)/1000000
        used = float(used)/1000000
        available = float(available)/1000000
        return size, available

    def getLocalDatetime(self):
        from_zone = tz.gettz('UTC')
        to_zone = tz.gettz('America/New_York')
        utc = datetime.utcnow()
        utc = utc.replace(tzinfo=from_zone)
        now = utc.astimezone(to_zone)
        return now