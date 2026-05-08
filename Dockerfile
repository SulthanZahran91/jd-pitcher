# Build stage
FROM golang:1.23-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o jd-pitcher .

# Run stage
FROM alpine:latest
RUN apk --no-cache add ca-certificates
WORKDIR /app
COPY --from=builder /app/jd-pitcher .
COPY --from=builder /app/web ./web
COPY --from=builder /app/config ./config
RUN mkdir -p data
EXPOSE 8080
CMD ["./jd-pitcher"]
