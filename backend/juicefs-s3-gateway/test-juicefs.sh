#!/bin/bash
# JuiceFS S3 Gateway 测试脚本

set -e

echo "========================================="
echo "JuiceFS S3 Gateway 连接测试"
echo "========================================="

# 配置
ENDPOINT="http://localhost:9003"
ACCESS_KEY="${JUICEFS_ACCESS_KEY:-juicefs}"
SECRET_KEY="${JUICEFS_SECRET_KEY:-juicefs123}"
BUCKET_NAME="test-bucket-$(date +%s)"
TEST_FILE="test-file-$(date +%s).txt"

echo ""
echo "配置信息:"
echo "  Endpoint: $ENDPOINT"
echo "  Access Key: $ACCESS_KEY"
echo "  Bucket: $BUCKET_NAME"
echo ""

# 检查依赖
if ! command -v aws &> /dev/null; then
    echo "错误: 未安装 AWS CLI"
    echo "安装方法: pip install awscli"
    exit 1
fi

# 配置 AWS CLI
export AWS_ACCESS_KEY_ID="$ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
export AWS_DEFAULT_REGION="us-east-1"

echo "步骤 1: 检查 JuiceFS S3 Gateway 是否可访问..."
if curl -sf "$ENDPOINT" > /dev/null 2>&1; then
    echo "✅ JuiceFS S3 Gateway 可访问"
else
    echo "❌ JuiceFS S3 Gateway 不可访问,请检查服务是否已启动"
    echo "   提示: 运行 'docker compose ps' 检查服务状态"
    exit 1
fi

echo ""
echo "步骤 2: 创建测试存储桶..."
if aws --endpoint-url "$ENDPOINT" s3 mb "s3://$BUCKET_NAME" 2>/dev/null; then
    echo "✅ 存储桶创建成功: $BUCKET_NAME"
else
    echo "❌ 存储桶创建失败"
    exit 1
fi

echo ""
echo "步骤 3: 创建测试文件并上传..."
echo "Hello, JuiceFS S3 Gateway! $(date)" > "/tmp/$TEST_FILE"
if aws --endpoint-url "$ENDPOINT" s3 cp "/tmp/$TEST_FILE" "s3://$BUCKET_NAME/$TEST_FILE" 2>/dev/null; then
    echo "✅ 文件上传成功: $TEST_FILE"
else
    echo "❌ 文件上传失败"
    rm -f "/tmp/$TEST_FILE"
    exit 1
fi

echo ""
echo "步骤 4: 列出存储桶中的对象..."
if aws --endpoint-url "$ENDPOINT" s3 ls "s3://$BUCKET_NAME/" | grep -q "$TEST_FILE"; then
    echo "✅ 文件列表正确"
    aws --endpoint-url "$ENDPOINT" s3 ls "s3://$BUCKET_NAME/"
else
    echo "❌ 文件列表失败"
    exit 1
fi

echo ""
echo "步骤 5: 下载文件并验证..."
if aws --endpoint-url "$ENDPOINT" s3 cp "s3://$BUCKET_NAME/$TEST_FILE" "/tmp/$TEST_FILE.downloaded" 2>/dev/null; then
    echo "✅ 文件下载成功"
    
    # 验证内容
    if diff "/tmp/$TEST_FILE" "/tmp/$TEST_FILE.downloaded" > /dev/null 2>&1; then
        echo "✅ 文件内容验证通过"
    else
        echo "❌ 文件内容不一致"
        exit 1
    fi
else
    echo "❌ 文件下载失败"
    exit 1
fi

echo ""
echo "步骤 6: 清理测试资源..."
aws --endpoint-url "$ENDPOINT" s3 rm "s3://$BUCKET_NAME/$TEST_FILE" 2>/dev/null
aws --endpoint-url "$ENDPOINT" s3 rb "s3://$BUCKET_NAME" 2>/dev/null
rm -f "/tmp/$TEST_FILE" "/tmp/$TEST_FILE.downloaded"
echo "✅ 清理完成"

echo ""
echo "========================================="
echo "✅ 所有测试通过! JuiceFS S3 Gateway 工作正常"
echo "========================================="
echo ""
echo "你现在可以使用以下凭证访问 S3 Gateway:"
echo "  Endpoint: $ENDPOINT"
echo "  Access Key: $ACCESS_KEY"
echo "  Secret Key: $SECRET_KEY"
echo ""
