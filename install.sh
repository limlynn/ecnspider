#!/bin/bash
sudo apt update
sudo apt install python3 python3-pip git -y
sudo apt install python3 python3-pip build-essential libbz2-dev libsqlite3-dev libreadline-dev zlib1g-dev libncurses5-dev libssl-dev libgdbm-dev liblzma-dev tk-dev -y
sudo pip3 install psutil dnspython3

git clone https://github.com/limlynn/ecnspider.git
cd ecnspider

sudo /sbin/sysctl -w net.ipv4.tcp_ecn=0

python3 new_subset.py 10000 10000 ./traceroute_ip_list.txt ./subset.csv
python3 resolution.py --workers 10 --www preferred ./subset.csv ./resolved.csv
python3 unique.py ./resolved.csv ./input.csv
ifconfig
# tcpdump -ni eth0 -w ./ecn_spider.pcap -s 128 && python3 ecn_spider.py --verbosity INFO --workers 1 --timeout 1 ./input.csv ./retry.csv ./ecn-spider.csv ./ecn-spider.log 
# --no-tcpdump-check