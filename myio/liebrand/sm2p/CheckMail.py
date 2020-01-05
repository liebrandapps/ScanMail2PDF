import base64
import email
import email.utils
import email.header
import hashlib
import hmac
import imaplib
import json
import logging
import os
import random
import re
import shutil
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler

import img2pdf
import ocrmypdf
import uuid
from urlextract import URLExtract
import tldextract

from myio.liebrand.sm2p.Config import Config


class DateTimeEncoder(json.JSONEncoder):

    def default(self, obj):
        if isinstance(obj, datetime):
            return {
                '__type__': 'seconds',
                'seconds': time.mktime(obj.timetuple()),
            }
        else:
            return json.JSONEncoder.default(self, obj)


class DateTimeDecoder(json.JSONDecoder):

    def __init__(self, *args, **kargs):
        json.JSONDecoder.__init__(self, object_hook=self.dict_to_object,
                                  *args, **kargs)

    def dict_to_object(self, d):
        if '__type__' not in d:
            return d

        return datetime.fromtimestamp(d['seconds'])

class ProcessPDF:

    SECTION = "ocr"

    def __init__(self, config, log):
        cfgDict = { ProcessPDF.SECTION : {
                "tmpPath": ["String", "/tmp"],
                "tagIn": ["String", ".in"],
                "tagOut": ["String", ".out"],
                "tagSidecar": ["String", ".sidecar.txt"],
                "suffix": ["String", ".pdf"],
                "deskew": ["Boolean", True],
                "removeBackground": ["Boolean", True],
                "destPath" : ["String", "/root/doc"]
            }
        }
        config.addScope(cfgDict)
        self.tmpPath = config.ocr_tmpPath
        self.tagIn = config.ocr_tagIn
        self.tagOut = config.ocr_tagOut
        self.tagSidecar = config.ocr_tagSidecar
        self.suffix = config.ocr_suffix
        self.deskew = config.ocr_deskew
        self.removeBackground = config.ocr_removeBackground
        self.destPath = config.ocr_destPath
        self.log = log

    def process(self, pdfData):
        inf, outf, sidef = self.store(pdfData)
        self.log.info("Creating file: %s" % outf)
        ocrmypdf.ocr(inf, outf, deskew=self.deskew, sidecar=sidef, remove_background=self.removeBackground,
                     language='deu')
        yr, mt, name = self.guess(sidef)
        destName = os.path.join(self.destPath, "%s %s %s" % (yr, mt, name))
        idx = 2
        orgName = destName
        while os.path.exists(destName):
            destName = "%s %02d" % (orgName, idx)
            idx+=1

        shutil.move(outf, destName)
        os.remove(inf)
        os.remove(sidef)

    def store(self, pdfData):
        fNameBase = os.path.join(self.tmpPath, str(uuid.uuid4()))
        inf = fNameBase + self.tagIn + self.suffix
        outf = fNameBase + self.tagOut + self.suffix
        sidef = fNameBase + self.tagSidecar
        with open(inf, 'wb') as fp:
            fp.write(pdfData)
        return inf, outf, sidef

    def guess(self, sidecar):
        with open(sidecar, 'r') as file:
            data = file.read()

        # date
        dt = re.findall("(\d{1,4}([.\-/])\d{1,2}([.\-/])\d{1,4})", data)
        if len(dt)>0:
            yr=dt[0][0][8:10]
            mt=dt[0][0][3:5]
        else:
            yr="YY"
            mt="MM"
        yr = yr.replace('/', 'x')
        mt = mt.replace('/', 'x')
        # url
        urlAddr = re.findall(r'(www|http)\S+', data)
        urlAddr = URLExtract().find_urls(data)
        print (urlAddr)
        if len(urlAddr) > 0:
            ext = tldextract.extract(urlAddr[0])
            name = ext.domain
        else:
            # email-address
            mailAddr = re.findall(r'[\w\.-]+@[\w\.-]+', data)
            #print (mailAddr)
            if len(mailAddr)>0:
                name = mailAddr[0].split('@')[1]
            else:
                name = "Doc Id %06d" % random.randint(1, 999999)
        name += '.pdf'
        return(yr,mt, name)


class CheckMail:

    SECTION = "sm2p"

    def __init__(self):
        cfgDict = {
            CheckMail.SECTION : {
                "logFileName": ["String", "/tmp/sm2p.log" ],
                "maxFileSize": ["Integer", 1024000],
                "msgFormat": ["String", "%(asctime)s, %(levelname)s, %(module)s {%(process)d}, %(lineno)d, %(message)s" ],
                "trustedSender" : ["Array", "scan@liebrand.io"],
                "userName" : [ "String", ],
                "password" : [ "String", ],
                "mailServer" : [ "String", ],
                "pin" : [ "String", "0000"],
                "hashBufferSize" : ["Integer", 1024],
                "hashStore" : [ "String", "./hash.db"]
            }
        }
        self.startTime=datetime.now()
        self.config=Config("./sm2p.ini")
        self.config.addScope(cfgDict)
        try:
            self.logFilename=self.config.sm2p_logFileName
            self.log=logging.Logger("sm2p")
            loghdl=RotatingFileHandler(self.logFilename, 'a', self.config.sm2p_maxFileSize, 4)
            loghdl.setFormatter(logging.Formatter(self.config.sm2p_msgFormat))
            loghdl.setLevel(logging.DEBUG)
            self.log.addHandler(loghdl)
        except Exception as e:
            print("Unable to initialize logging system. Reason: %s" % e)
            sys.exit()


    def retrieveMail(self):
        trustedSender = self.config.sm2p_trustedSender

        db = self.config.sm2p_hashStore
        if os.path.exists(db) and os.path.isfile(db) and os.stat(db).st_size > 0:
            with open(db) as fp:
                hashes = json.load(fp, cls=DateTimeDecoder)
        else:
            hashes = {}

        mail = imaplib.IMAP4_SSL(self.config.sm2p_mailServer)
        mail.login(self.config.sm2p_userName, self.config.sm2p_password)
        lst = mail.list()
        mail.select("inbox")

        result, data = mail.uid('search', None, '(UNSEEN SUBJECT ' + self.config.sm2p_pin + ')')  # (ALL/UNSEEN)
        i = len(data[0].split())

        for x in range(i):
            latest_email_uid = data[0].split()[x]
            # print latest_email_uid
            result, email_data = mail.uid('fetch', latest_email_uid, '(RFC822)')
            # result, email_data = conn.store(num,'-FLAGS','\\Seen')
            # this might work to set flag to seen, if it doesn't already
            raw_email = email_data[0][1]
            raw_email_string = raw_email.decode('utf-8')
            email_message = email.message_from_string(raw_email_string)

            # Header Details
            date_tuple = email.utils.parsedate_tz(email_message['Date'])
            if date_tuple:
                local_date = datetime.fromtimestamp(email.utils.mktime_tz(date_tuple))
                local_message_date = "%s" % (str(local_date.strftime("%a, %d %b %Y %H:%M:%S")))
            emailFrom = str(email.header.make_header(email.header.decode_header(email_message['From'])))
            email_to = str(email.header.make_header(email.header.decode_header(email_message['To'])))
            subject = str(email.header.make_header(email.header.decode_header(email_message['Subject'])))

            found = False
            for ts in trustedSender:
                if ts.upper() in emailFrom.upper():
                    found = True
                    p = re.compile('[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', re.IGNORECASE)
                    returnMail = re.findall(p, ts)[0]
                    break
            if not (found):
                print (emailFrom)
                continue

            self.log.debug("Received email from %s" % (returnMail))

            # Body details
            attachments = []
            done = False
            for part in email_message.walk():
                #print(part.get_content_type())
                if part.get('Content-Type') == "application/pdf":
                    encMsg = part.get_payload(decode=True)
                    # print len(encMsg)
                    hsh = base64.b64encode(
                        hmac.new(bytes("1234567890", "UTF-8"), encMsg, hashlib.sha256).digest())
                    if hsh in hashes.keys():
                        errMessage = "Saw same message again (hash %s)" % (hsh)
                        self.log.error(errMessage)
                        hasErr = True
                        break
                    else:
                        p = ProcessPDF(self.config, self.log)
                        p.process(encMsg)
                        now = datetime.now()
                        hashes[hsh] = now
                        while len(hashes) > self.config.sm2p_hashBufferSize:
                            oldestHash = ""
                            oldest = now
                            for k in hashes.keys():
                                if hashes[k] < oldest:
                                    oldestHash = k
                                    oldest = hashes[k]
                                if len(oldestHash) > 0:
                                    del oldestHash[hashes]
                            with open(db + "_tmp", 'w') as fp:
                                json.dump(hashes, fp, cls=DateTimeEncoder)
                            os.rename(db + "_tmp", db)
                elif part.get_content_type() == "image/jpeg":
                    attachments.append(part.get_payload(decode=True))
                else:
                    continue
            if len(attachments) > 0:
                pdf = img2pdf.convert(attachments)
                ProcessPDF(self.config, self.log).process(pdf)

    def processFiles(self, sourcePath):
        p = ProcessPDF(self.config, self.log)
        for file in os.listdir(sourcePath):
            if file.endswith(".pdf") or file.endswith(".PDF"):
                with open(os.path.join(sourcePath, file), 'rb') as file:
                    data = file.read()
                    p.process(data)


if __name__ == '__main__':
    if len(sys.argv)>1:
        sourcePath = sys.argv[1]
        if(os.path.exists(sourcePath) and os.path.isdir(sourcePath)):
            CheckMail().processFiles(sourcePath)
        else:
            print("Path %s is invalid" % sourcePath)
    else:
        CheckMail().retrieveMail()
