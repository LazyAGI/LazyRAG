# Copyright 2021 Juicedata Inc
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM golang:1.23-bullseye as binaryimage

ARG GOPROXY

# 安装基本构建依赖
RUN apt-get update && \
    apt-get install -y build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
ENV GOPROXY=https://goproxy.cn,direct
COPY . .
RUN go env -w GO111MODULE=on \
    && go env -w GOPROXY=https://goproxy.cn,direct
RUN go version && cd juicefs && go mod tidy && make

# 运行时镜像
FROM debian:bullseye-slim

# 安装运行时依赖
RUN apt-get update && \
    apt-get install -y ca-certificates fuse && \
    rm -rf /var/lib/apt/lists/*

# 从构建阶段复制二进制文件
COPY --from=binaryimage /workspace/juicefs/juicefs /usr/local/bin/juicefs
RUN chmod +x /usr/local/bin/juicefs && \
    ln -sf /usr/local/bin/juicefs /bin/mount.juicefs && \
    /usr/local/bin/juicefs --version

# 设置入口点
ENTRYPOINT ["/usr/local/bin/juicefs"]
