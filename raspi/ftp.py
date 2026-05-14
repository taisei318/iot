from ftplib import FTP

_ftp = FTP('169.254.84.84')
_ftp.login('user','password')
print(_ftp.retrlines('LIST'))
_file = open ('ex.csv', 'rb')
_ftp.cwd('/C:\\Users\\reino\\Downloads\\ex-3/')
_ftp.storbinary('STOR ex_rcv.csv', _file)
_file.close()
_ftp.quit()
