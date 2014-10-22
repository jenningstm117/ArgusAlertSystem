import Argus

def Main():
    email_creds = ('********@gmail.com', '**********')
    argusAlert = Argus('/home/pi', email_creds)
    argusAlert.Start()

if __name__ == '__main__':
    Main()