#include <arpa/inet.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netdb.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

int main(int ac, char**av) {
	int i;
	struct addrinfo *res, *rp;
	struct addrinfo hints;
	char host[NI_MAXHOST];
	int e;

	memset(&hints, 0, sizeof(struct addrinfo));
	hints.ai_family = AF_UNSPEC;
	hints.ai_socktype = SOCK_STREAM;
	for(i=1;i<ac;i++) {
		res=NULL;
		if((e=getaddrinfo(av[i], 0, &hints, &res))) {
			printf("Error on %s: %s\n", av[i], gai_strerror(e));
		} else {
			for(rp=res; rp != NULL; rp = rp->ai_next) {
				struct sockaddr_in* in4;
				struct sockaddr_in6* in6;
				void* addr;

				switch(rp->ai_family) {
				case AF_INET:
					in4 = (struct sockaddr_in*)rp->ai_addr;
					addr = &(in4->sin_addr);
					break;
				case AF_INET6:
					in6 = (struct sockaddr_in6*)rp->ai_addr;
					addr = &(in6->sin6_addr);
					break;
				default:
					continue;
				}
				inet_ntop(rp->ai_family, addr, host, sizeof(host));
				printf("%s\n", host);
			}
		}
		if(res)freeaddrinfo(res);
	}
	return 0;
}
