FROM golang:1.24-alpine AS build
WORKDIR /app

# 配置国内源
ENV GOPROXY=https://goproxy.cn,direct
ENV GOSUMDB=sum.golang.google.cn

COPY core/ ./
RUN CGO_ENABLED=0 go build -o /core .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates wget
COPY --from=build /core /core
EXPOSE 8000
CMD ["/core"]
