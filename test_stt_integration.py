#!/usr/bin/env python3
# test_stt_integration.py
"""
Deepgram STT集成测试脚本

测试双STT引擎系统的各种功能：
- 配置验证
- 引擎创建和连接
- 基本功能测试
- 错误处理测试
"""

import os
import sys
import time
import asyncio
from typing import List

# 导入我们的模块
from config import Config
from stt_factory import STTFactory, create_stt_stream
from stt_base import STTStatus

class STTTestRunner:
    """STT系统测试运行器"""
    
    def __init__(self):
        self.test_results = []
        self.partial_results = []
        self.final_results = []
        
    def on_partial(self, text: str, lang: str):
        """处理部分结果"""
        result = f"Partial: {text} ({lang})"
        print(f"[Test] {result}")
        self.partial_results.append((text, lang, time.time()))
        
    def on_final(self, text: str, lang: str):
        """处理最终结果"""
        result = f"Final: {text} ({lang})"
        print(f"[Test] {result}")
        self.final_results.append((text, lang, time.time()))
    
    def run_test(self, test_name: str, test_func) -> bool:
        """运行单个测试"""
        print(f"\n{'='*60}")
        print(f"运行测试: {test_name}")
        print(f"{'='*60}")
        
        try:
            start_time = time.time()
            result = test_func()
            duration = time.time() - start_time
            
            if result:
                print(f"✅ 测试通过: {test_name} (用时: {duration:.2f}s)")
                self.test_results.append((test_name, True, duration, None))
                return True
            else:
                print(f"❌ 测试失败: {test_name} (用时: {duration:.2f}s)")
                self.test_results.append((test_name, False, duration, "测试返回False"))
                return False
                
        except Exception as e:
            duration = time.time() - start_time if 'start_time' in locals() else 0
            print(f"❌ 测试异常: {test_name} - {e} (用时: {duration:.2f}s)")
            self.test_results.append((test_name, False, duration, str(e)))
            return False
    
    def test_config_validation(self) -> bool:
        """测试配置验证"""
        print("1. 测试配置管理...")
        
        # 显示配置摘要
        Config.print_config_summary()
        
        # 验证配置
        validation = Config.validate_config()
        print(f"配置验证结果: {validation}")
        
        if not validation["valid"]:
            print(f"配置错误: {validation['errors']}")
            return False
            
        return True
    
    def test_engine_availability(self) -> bool:
        """测试引擎可用性"""
        print("2. 测试引擎可用性...")
        
        # 获取引擎状态
        engines = STTFactory.get_available_engines()
        
        available_engines = []
        for engine, info in engines.items():
            if info["available"]:
                available_engines.append(engine)
                print(f"✅ {engine.value}: 可用 - {info['description']}")
            else:
                print(f"❌ {engine.value}: 不可用 - {info.get('error', '未知错误')}")
        
        if not available_engines:
            print("❌ 没有可用的STT引擎")
            return False
            
        print(f"✅ 发现 {len(available_engines)} 个可用引擎")
        return True
    
    def test_stt_creation(self) -> bool:
        """测试STT实例创建"""
        print("3. 测试STT实例创建...")
        
        try:
            # 创建STT实例
            stt = create_stt_stream(
                on_partial=self.on_partial,
                on_final=self.on_final,
                debug=True
            )
            
            print(f"✅ 成功创建STT实例: {stt.__class__.__name__}")
            print(f"   状态: {stt.get_status()}")
            
            # 测试基本属性
            print(f"   语言: {stt.language}")
            print(f"   采样率: {stt.sample_rate}Hz")
            
            # 清理
            if hasattr(stt, 'close'):
                stt.close()
            
            return True
            
        except Exception as e:
            print(f"❌ 创建STT实例失败: {e}")
            return False
    
    def test_stt_connection(self) -> bool:
        """测试STT连接"""
        print("4. 测试STT连接...")
        
        try:
            # 创建STT实例
            stt = create_stt_stream(
                on_partial=self.on_partial,
                on_final=self.on_final,
                debug=True
            )
            
            # 测试连接
            print("尝试连接...")
            connected = stt.connect()
            
            if connected:
                print(f"✅ 连接成功")
                print(f"   连接状态: {stt.get_status()}")
                print(f"   健康状态: {'健康' if stt.is_healthy() else '不健康'}")
                
                # 等待一下让连接稳定
                time.sleep(2)
                
                # 再次检查状态
                print(f"   2秒后状态: {stt.get_status()}")
                print(f"   2秒后健康: {'健康' if stt.is_healthy() else '不健康'}")
                
                result = True
            else:
                print(f"❌ 连接失败")
                result = False
            
            # 清理
            stt.close()
            print(f"   关闭后状态: {stt.get_status()}")
            
            return result
            
        except Exception as e:
            print(f"❌ 连接测试异常: {e}")
            return False
    
    def test_stt_stats(self) -> bool:
        """测试STT统计功能"""
        print("5. 测试STT统计功能...")
        
        try:
            stt = create_stt_stream(
                on_partial=self.on_partial,
                on_final=self.on_final,
                debug=True
            )
            
            # 连接
            if not stt.connect():
                print("❌ 无法连接，跳过统计测试")
                return False
            
            # 获取初始统计
            initial_stats = stt.get_stats()
            print("初始统计信息:")
            for key, value in initial_stats.items():
                if isinstance(value, dict):
                    print(f"  {key}:")
                    for sub_key, sub_value in value.items():
                        print(f"    {sub_key}: {sub_value}")
                else:
                    print(f"  {key}: {value}")
            
            # 模拟一些音频数据推送
            test_data = b'\x00' * 1600  # 1600字节的静音数据，约100ms
            
            for i in range(5):
                success = stt.push(test_data)
                if success:
                    print(f"✅ 推送测试数据 {i+1}/5")
                else:
                    print(f"❌ 推送失败 {i+1}/5")
                
                time.sleep(0.1)
            
            # 等待处理
            time.sleep(1)
            
            # 获取最终统计
            final_stats = stt.get_stats()
            print("\n最终统计信息:")
            bytes_sent = final_stats.get('total_bytes_sent', 0)
            runtime = final_stats.get('runtime', 0)
            print(f"  运行时间: {runtime:.2f}s")
            print(f"  发送字节数: {bytes_sent}")
            print(f"  状态: {final_stats.get('status', '未知')}")
            
            # 清理
            stt.close()
            
            return bytes_sent > 0  # 如果发送了数据就算成功
            
        except Exception as e:
            print(f"❌ 统计测试异常: {e}")
            return False
    
    def test_engine_switching(self) -> bool:
        """测试引擎切换"""
        print("6. 测试引擎切换...")
        
        # 获取可用引擎
        engines = STTFactory.get_available_engines()
        available = [engine for engine, info in engines.items() if info["available"]]
        
        if len(available) < 1:
            print("❌ 没有足够的可用引擎进行切换测试")
            return False
        
        success_count = 0
        
        for engine in available:
            try:
                print(f"测试引擎: {engine.value}")
                
                # 创建指定引擎的STT实例
                stt = create_stt_stream(
                    on_partial=self.on_partial,
                    on_final=self.on_final,
                    engine=engine.value,
                    debug=True
                )
                
                print(f"  创建成功: {stt.__class__.__name__}")
                
                # 尝试连接
                if stt.connect():
                    print(f"  ✅ {engine.value} 引擎连接成功")
                    success_count += 1
                    
                    # 测试基本功能
                    stats = stt.get_stats()
                    print(f"  引擎类型: {stats.get('engine', '未知')}")
                    
                else:
                    print(f"  ❌ {engine.value} 引擎连接失败")
                
                # 清理
                stt.close()
                
            except Exception as e:
                print(f"  ❌ {engine.value} 引擎测试异常: {e}")
        
        print(f"引擎测试完成: {success_count}/{len(available)} 成功")
        return success_count > 0
    
    def run_all_tests(self):
        """运行所有测试"""
        print("开始Deepgram STT集成测试")
        print(f"Python版本: {sys.version}")
        print(f"工作目录: {os.getcwd()}")
        
        # 定义测试列表
        tests = [
            ("配置验证", self.test_config_validation),
            ("引擎可用性", self.test_engine_availability),
            ("STT实例创建", self.test_stt_creation),
            ("STT连接测试", self.test_stt_connection),
            ("STT统计功能", self.test_stt_stats),
            ("引擎切换测试", self.test_engine_switching),
        ]
        
        # 运行测试
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            if self.run_test(test_name, test_func):
                passed += 1
        
        # 显示最终结果
        print(f"\n{'='*60}")
        print("测试结果汇总")
        print(f"{'='*60}")
        
        for test_name, success, duration, error in self.test_results:
            status = "✅ 通过" if success else "❌ 失败"
            print(f"{status} {test_name} ({duration:.2f}s)")
            if error and not success:
                print(f"     错误: {error}")
        
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if self.partial_results:
            print(f"收到 {len(self.partial_results)} 个部分结果")
        if self.final_results:
            print(f"收到 {len(self.final_results)} 个最终结果")
        
        success_rate = (passed / total) * 100
        print(f"成功率: {success_rate:.1f}%")
        
        if passed == total:
            print("\n🎉 所有测试通过！Deepgram STT集成成功")
            return True
        else:
            print(f"\n⚠️ {total - passed} 个测试失败，请检查配置和依赖")
            return False


def main():
    """主函数"""
    print("Deepgram STT集成测试")
    print("=" * 60)
    
    # 检查环境变量
    print("检查环境变量:")
    google_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    deepgram_key = os.getenv("DEEPGRAM_API_KEY")
    stt_engine = os.getenv("STT_ENGINE", "google")
    
    print(f"  GOOGLE_APPLICATION_CREDENTIALS: {'已设置' if google_creds else '未设置'}")
    print(f"  DEEPGRAM_API_KEY: {'已设置' if deepgram_key else '未设置'}")
    print(f"  STT_ENGINE: {stt_engine}")
    
    if not google_creds and not deepgram_key:
        print("\n⚠️ 警告: 没有设置任何STT服务的凭据")
        print("请设置以下环境变量之一:")
        print("  - GOOGLE_APPLICATION_CREDENTIALS (Google STT)")
        print("  - DEEPGRAM_API_KEY (Deepgram STT)")
    
    # 运行测试
    runner = STTTestRunner()
    success = runner.run_all_tests()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())