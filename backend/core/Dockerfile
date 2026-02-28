FROM golang:1.21-alpine AS build
WORKDIR /app
COPY core/go.mod core/main.go ./
RUN CGO_ENABLED=0 go build -o /core .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates
COPY --from=build /core /core
EXPOSE 8000
CMD ["/core"]
