FROM python:3.8.0-slim-buster
#安装requests PyExecJs 依赖
RUN pip3 install PyExecJS -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip3 install requests -i https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip3 install sanic -i https://pypi.tuna.tsinghua.edu.cn/simple
#工作目录
WORKDIR /app
#复制代码
COPY . .
#暴露端口
EXPOSE 5000
#暴露目录
VOLUME ["/app"]
#运行项目
CMD ["python3","/app/webserver.py","-p","5000"]
