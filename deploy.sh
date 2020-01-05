#!/usr/bin/env bash

rsync -avzr -e ssh myio/ root@192.168.0.185:./dev/ScanMail2PDF/myio/
rsync -avzr -e ssh sm2p.ini  root@192.168.0.185:./dev/ScanMail2PDF