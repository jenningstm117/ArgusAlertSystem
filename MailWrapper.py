import smtplib, types, os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.MIMEBase import MIMEBase
from email import Encoders

class MailWrapper(object):
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.sender = username
        self.d_receivers={}

    def setSender(self, sender):
        self.sender=sender

    def addReceiver(self, receiver):
        if not self.d_receivers.has_key(receiver):
            self.d_receivers[receiver]=receiver

    def removeReceiver(self, receiver):
        if self.d_receivers.has_key(receiver):
            del(self.d_receivers[receiver])

    def clearReceivers(self):
        del(self.receivers)
        self.receivers={}

    def attachFile(self, file_name):
        part = MIMEBase('application', "octet-stream")
        part.set_payload( open(file_name,"rb").read() )
        Encoders.encode_base64(part)
        part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(file_name))
        self.msg.attach(part)

    def createMail(self, subject, message):
        self.msg=MIMEMultipart()
        self.msg['Subject']=subject
        self.msg.attach(MIMEText(message))

    def sendMail(self):
        try:
            server = smtplib.SMTP('smtp.gmail.com:587')
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.sender, self.d_receivers.values(), self.msg.as_string())
            print 'Message sent successfully'
        except Exception as E:
            print 'Message failed to send'
            print E
        finally:
            server.quit()