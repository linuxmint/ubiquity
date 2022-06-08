#!/bin/sh

release=${RELEASE:-`lsb_release -cs`}
for host in *.com;
do
	echo "== $host ==";
	for dist in ${release} ${release}-proposed ${release}-updates ${release}-security;
	do
		mkdir -vp "${host}/${dist}"
		ubuntu_path="ubuntu/"
		if [ "${host}" = "ports.ubuntu.com" ]; then
			ubuntu_path=""
		fi
		
		wget -O "${host}/${dist}/Release" http://$host/${ubuntu_path}dists/$dist/Release
		wget -O "${host}/${dist}/Release.gpg" http://$host/${ubuntu_path}dists/$dist/Release.gpg
		wget -O "${host}/${dist}/InRelease" http://$host/${ubuntu_path}dists/$dist/InRelease
	done
done
