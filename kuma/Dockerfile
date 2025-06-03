FROM louislam/uptime-kuma:1

COPY init_admin.sh /init_admin.sh
RUN chmod +x /init_admin.sh

ENTRYPOINT ["/init_admin.sh"]
