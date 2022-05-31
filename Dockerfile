FROM python:3.9.13-alpine3.16
#安装requests PyExecJs 依赖
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.ustc.edu.cn/g' /etc/apk/repositories && apk update && apk --no-cache add build-base && \
    pip3 install PyExecJS -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip3 install requests -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    apk add git
#工作目录
WORKDIR /app
#拉取项目
RUN git clone https://mirror.ghproxy.com/https://github.com/rain-dl/real-url-proxy-server.git
#暴露端口
EXPOSE 5000
#暴露目录
VOLUME ["/app"]
#运行项目
CMD ["python3","/app/real-url-proxy-server/webserver.py","-p","5000"]
