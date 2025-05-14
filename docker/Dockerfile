FROM python:3.9-alpine

COPY ../requirements.txt /app/requirements.txt

WORKDIR /app

RUN echo 'http://dl-cdn.alpinelinux.org/alpine/v3.9/main' >> /etc/apk/repositories
RUN echo 'http://dl-cdn.alpinelinux.org/alpine/v3.9/community' >> /etc/apk/repositories
RUN apk add --update --no-cache --virtual .tmp-build-deps \
    gcc libc-dev linux-headers postgresql-dev mongodb mongodb-tools openssh \
    nginx supervisor gettext traceroute curl && apk add libffi-dev

# Install WireGuard and iptables
RUN apk add --no-cache wireguard-tools iptables ip6tables envsubst

RUN pip3 install --upgrade pip
RUN pip3 install uwsgi
RUN pip install -r requirements.txt

RUN rm -r /root/.cache

COPY ../docker/nginx.conf /etc/nginx/
COPY ../docker/flask-site-nginx.conf /etc/nginx/conf.d/
COPY ../docker/uwsgi.ini /etc/uwsgi/
COPY ../docker/supervisord.conf /etc/

RUN mkdir -p /data/db && \
    chown -R mongodb /data/db
VOLUME /data/db
EXPOSE 27017

# Set up default timezone
ENV TZ UTC
RUN apk add --no-cache tzdata && \
    cp /usr/share/zoneinfo/$TZ /etc/localtime && \
    echo $TZ > /etc/timezone

# Create WireGuard configuration directory
RUN mkdir -p /etc/wireguard

# Add WireGuard configurations
COPY ../docker/wireguard-prod.conf /etc/wireguard/prod.conf.template
COPY ../docker/wireguard-dev.conf /etc/wireguard/dev.conf.template

# Add WireGuard startup script
COPY ../docker/start_wireguard.sh /app/start_wireguard.sh
RUN chmod +x /app/start_wireguard.sh

COPY ../app app
COPY ../docker/wsgi.py wsgi.py

# Use a custom entrypoint to start WireGuard before supervisord
COPY ../docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]