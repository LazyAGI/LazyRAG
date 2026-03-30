

import axios from "axios";
import { AgentAppsAuth } from "@/components/auth";
import { axiosInstance } from "@/components/request";


export async function testAutoRefresh() {
  console.log("=== 测试自动刷新 ===");
  
  const userInfo = AgentAppsAuth.getUserInfo();
  if (!userInfo) {
    console.error("❌ 未登录，无法测试");
    return;
  }

  console.log("📝 当前 access_token:", userInfo.token?.substring(0, 20) + "...");
  console.log("📝 当前 refresh_token:", userInfo.refreshToken?.substring(0, 20) + "...");

  const oldAccessToken = userInfo.token;
  const oldRefreshToken = userInfo.refreshToken;

  AgentAppsAuth.updateUserInfo({
    token: "expired.invalid.token",
  });

  console.log("🔧 已将 access_token 修改为无效值");

  try {
    console.log("🚀 发起测试请求...");
    await axiosInstance.get("/api/authservice/auth/me");
    
    const newUserInfo = AgentAppsAuth.getUserInfo();
    console.log("✅ 请求成功！");
    console.log("📝 新 access_token:", newUserInfo?.token?.substring(0, 20) + "...");
    console.log("📝 新 refresh_token:", newUserInfo?.refreshToken?.substring(0, 20) + "...");

    if (newUserInfo?.token !== oldAccessToken) {
      console.log("✅ access_token 已更新");
    }
    if (newUserInfo?.refreshToken !== oldRefreshToken) {
      console.log("✅ refresh_token 已轮换");
    }

    console.log("🎉 自动刷新测试通过！");
  } catch (error) {
    console.error("❌ 测试失败:", error);
    
    AgentAppsAuth.updateUserInfo({
      token: oldAccessToken,
      refreshToken: oldRefreshToken,
    });
  }
}


export async function testConcurrentRefresh() {
  console.log("=== 测试并发刷新控制 ===");

  const userInfo = AgentAppsAuth.getUserInfo();
  if (!userInfo) {
    console.error("❌ 未登录，无法测试");
    return;
  }

  const oldAccessToken = userInfo.token;
  const oldRefreshToken = userInfo.refreshToken;

  AgentAppsAuth.updateUserInfo({
    token: "expired.invalid.token",
  });

  console.log("🔧 已将 access_token 修改为无效值");

  let refreshCount = 0;
  
  let refreshCallCount = 0;
  const originalCreate = axios.create;
  (axios as any).create = (...args: any[]) => {
    const instance = originalCreate.apply(axios, args);
    const originalPost = instance.post;
    instance.post = async (url: string, ...rest: any[]) => {
      if (url?.includes("/auth/refresh")) {
        refreshCallCount++;
        refreshCount = refreshCallCount;
        console.log(`📡 刷新请求 #${refreshCount}`);
      }
      return originalPost.call(instance, url, ...rest);
    };
    return instance;
  };

  try {
    console.log("🚀 同时发起 5 个请求...");
    const promises = Array.from({ length: 5 }, (_, i) =>
      axiosInstance.get("/api/authservice/auth/me").then(() => {
        console.log(`✅ 请求 #${i + 1} 成功`);
      })
    );

    await Promise.all(promises);

    console.log(`📊 总共触发了 ${refreshCount} 次刷新请求`);
    
    if (refreshCount === 1) {
      console.log("🎉 并发控制测试通过！只刷新了 1 次");
    } else {
      console.warn(`⚠️  预期刷新 1 次，实际刷新了 ${refreshCount} 次`);
    }
  } catch (error) {
    console.error("❌ 测试失败:", error);
  } finally {
    (axios as any).create = originalCreate;
    
    AgentAppsAuth.updateUserInfo({
      token: oldAccessToken,
      refreshToken: oldRefreshToken,
    });
  }
}


export async function testRefreshMethod() {
  console.log("=== 测试刷新方法 ===");

  const userInfo = AgentAppsAuth.getUserInfo();
  if (!userInfo) {
    console.error("❌ 未登录，无法测试");
    return;
  }

  console.log("📝 刷新前 access_token:", userInfo.token?.substring(0, 20) + "...");
  console.log("📝 刷新前 refresh_token:", userInfo.refreshToken?.substring(0, 20) + "...");

  try {
    const newAccessToken = await AgentAppsAuth.refreshAccessToken();
    
    const newUserInfo = AgentAppsAuth.getUserInfo();
    console.log("✅ 刷新成功！");
    console.log("📝 刷新后 access_token:", newUserInfo?.token?.substring(0, 20) + "...");
    console.log("📝 刷新后 refresh_token:", newUserInfo?.refreshToken?.substring(0, 20) + "...");

    if (newUserInfo?.token === newAccessToken) {
      console.log("✅ Token 已更新到本地存储");
    }

    console.log("🎉 刷新方法测试通过！");
  } catch (error) {
    console.error("❌ 测试失败:", error);
  }
}


export function showTokenInfo() {
  console.log("=== 当前 Token 信息 ===");
  
  const userInfo = AgentAppsAuth.getUserInfo();
  if (!userInfo) {
    console.log("❌ 未登录");
    return;
  }

  console.log("👤 用户名:", userInfo.username);
  console.log("🆔 用户ID:", userInfo.userId);
  console.log("👔 角色:", userInfo.role);
  console.log("📝 Access Token:", userInfo.token?.substring(0, 30) + "...");
  console.log("🔄 Refresh Token:", userInfo.refreshToken?.substring(0, 30) + "...");
  
  if (userInfo.timestamp) {
    const loginTime = new Date(userInfo.timestamp);
    const now = new Date();
    const minutes = Math.floor((now.getTime() - loginTime.getTime()) / 60000);
    console.log(`⏰ 登录时间: ${loginTime.toLocaleString()} (${minutes} 分钟前)`);
  }

  try {
    const [, payload] = userInfo.token.split(".");
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    
    if (decoded.exp) {
      const expTime = new Date(decoded.exp * 1000);
      const now = new Date();
      const remainMinutes = Math.floor((expTime.getTime() - now.getTime()) / 60000);
      
      console.log(`⏱️  Token 过期时间: ${expTime.toLocaleString()}`);
      
      if (remainMinutes > 0) {
        console.log(`⏱️  剩余有效时间: ${remainMinutes} 分钟`);
      } else {
        console.log(`⚠️  Token 已过期 ${Math.abs(remainMinutes)} 分钟`);
      }
    }
  } catch (error) {
    console.log("ℹ️  无法解析 Token 过期时间");
  }
}


export async function runAllTests() {
  console.log("\n");
  console.log("=".repeat(50));
  console.log("开始 Token 刷新机制完整测试");
  console.log("=".repeat(50));
  console.log("\n");

  showTokenInfo();
  console.log("\n");

  await testRefreshMethod();
  console.log("\n");

  await testAutoRefresh();
  console.log("\n");

  await testConcurrentRefresh();
  console.log("\n");

  console.log("=".repeat(50));
  console.log("所有测试完成");
  console.log("=".repeat(50));
}

if (import.meta.env.DEV && typeof window !== "undefined") {
  (window as any).testTokenRefresh = {
    testAutoRefresh,
    testConcurrentRefresh,
    testRefreshMethod,
    showTokenInfo,
    runAllTests,
  };
  
  console.log("💡 Token 刷新测试工具已加载到 window.testTokenRefresh");
  console.log("   可用方法:");
  console.log("   - window.testTokenRefresh.showTokenInfo()");
  console.log("   - window.testTokenRefresh.testRefreshMethod()");
  console.log("   - window.testTokenRefresh.testAutoRefresh()");
  console.log("   - window.testTokenRefresh.testConcurrentRefresh()");
  console.log("   - window.testTokenRefresh.runAllTests()");
}
