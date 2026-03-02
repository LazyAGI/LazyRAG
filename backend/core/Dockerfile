FROM golang:1.22-alpine AS build
WORKDIR /app
COPY core/ ./
RUN CGO_ENABLED=0 go build -o /core .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates
COPY --from=build /core /core
EXPOSE 8000
CMD ["/core"]
