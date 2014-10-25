import Argus, ArgusPIR

def Main():
    email_creds = ('*******@gmail.com', '********')
    #argusAlert = Argus.Argus('/home/pi', email_creds)
    #argusAlert.Start()

    argusPirAlert = ArgusPIR.ArgusPIR('/home/pi', email_creds)
    argusPirAlert.Start()


if __name__ == '__main__':
    Main()