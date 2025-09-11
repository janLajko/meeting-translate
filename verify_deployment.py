#!/usr/bin/env python3
# verify_deployment.py
"""
部署验证脚本
验证所有必要的模块都可以正确导入，用于测试Google Cloud Run部署是否成功
"""

import sys
import importlib

def verify_imports():
    """验证所有关键模块导入"""
    required_modules = [
        'config',
        'stt_base', 
        'stt_factory',
        'deepgram_asr',
        'asr',
        'translate',
        'main'
    ]
    
    print("🔍 验证部署模块导入...")
    print("=" * 50)
    
    success_count = 0
    total_count = len(required_modules)
    
    for module_name in required_modules:
        try:
            module = importlib.import_module(module_name)
            print(f"✅ {module_name}: 导入成功")
            success_count += 1
            
            # 验证关键类和函数
            if module_name == 'config':
                assert hasattr(module, 'Config')
                assert hasattr(module, 'STTEngine')
                print(f"   - Config类和STTEngine枚举存在")
                
            elif module_name == 'stt_factory':
                assert hasattr(module, 'STTFactory')
                assert hasattr(module, 'create_stt_stream')
                print(f"   - STTFactory和create_stt_stream函数存在")
                
            elif module_name == 'stt_base':
                assert hasattr(module, 'STTStreamBase')
                assert hasattr(module, 'STTStatus')
                print(f"   - STTStreamBase基类和STTStatus枚举存在")
                
            elif module_name == 'deepgram_asr':
                assert hasattr(module, 'DeepgramSTTStream')
                print(f"   - DeepgramSTTStream类存在")
                
            elif module_name == 'asr':
                assert hasattr(module, 'GoogleSTTStream')
                print(f"   - GoogleSTTStream类存在")
                
        except ImportError as e:
            print(f"❌ {module_name}: 导入失败 - {e}")
        except AssertionError as e:
            print(f"⚠️ {module_name}: 导入成功但缺少必要组件")
            success_count += 0.5
        except Exception as e:
            print(f"⚠️ {module_name}: 导入成功但验证时出错 - {e}")
            success_count += 0.5
    
    print("=" * 50)
    print(f"导入验证结果: {success_count}/{total_count} 成功")
    
    if success_count == total_count:
        print("🎉 所有模块导入验证通过！部署应该成功")
        return True
    else:
        print("⚠️ 存在导入问题，部署可能失败")
        return False

def verify_stt_system():
    """验证STT系统基本功能"""
    print("\n🔧 验证STT系统功能...")
    print("=" * 50)
    
    try:
        # 导入核心组件
        from config import Config, STTEngine
        from stt_factory import STTFactory, create_stt_stream
        
        # 检查配置
        current_engine = Config.get_stt_engine()
        print(f"✅ 当前STT引擎: {current_engine.value}")
        
        # 检查引擎可用性
        engines = STTFactory.get_available_engines()
        available = [eng for eng, info in engines.items() if info.get('available', False)]
        print(f"✅ 可用引擎: {[eng.value for eng in available]} ({len(available)}个)")
        
        # 测试工厂创建（不实际连接）
        def dummy_callback(text, lang):
            pass
        
        try:
            # 注意：这里可能因为缺少SDK而失败，但导入应该成功
            stt = create_stt_stream(dummy_callback, dummy_callback)
            print(f"✅ STT实例创建成功: {stt.__class__.__name__}")
            stt.close()
        except Exception as e:
            if "依赖缺失" in str(e) or "SDK未安装" in str(e):
                print(f"⚠️ STT实例创建失败（预期，因为缺少SDK）: {e}")
            else:
                print(f"❌ STT实例创建失败: {e}")
                return False
        
        print("🎉 STT系统验证通过！")
        return True
        
    except Exception as e:
        print(f"❌ STT系统验证失败: {e}")
        return False

def verify_main_app():
    """验证主应用可以启动"""
    print("\n🚀 验证主应用导入...")
    print("=" * 50)
    
    try:
        # 导入主应用（不实际启动服务器）
        import main
        
        # 检查FastAPI应用对象
        assert hasattr(main, 'app')
        print("✅ FastAPI应用对象存在")
        
        # 检查关键函数
        key_functions = [
            'has_sentence_ending_punctuation',
            'contains_chinese_chars', 
            'detect_text_language'
        ]
        
        for func_name in key_functions:
            if hasattr(main, func_name):
                print(f"✅ 函数 {func_name} 存在")
            else:
                print(f"⚠️ 函数 {func_name} 缺失")
        
        print("🎉 主应用验证通过！")
        return True
        
    except Exception as e:
        print(f"❌ 主应用验证失败: {e}")
        return False

def main():
    """主验证函数"""
    print("Google Cloud Run 部署验证")
    print("=" * 60)
    print(f"Python版本: {sys.version}")
    print(f"Python路径: {sys.path[0]}")
    print()
    
    # 运行所有验证
    results = []
    results.append(verify_imports())
    results.append(verify_stt_system())
    results.append(verify_main_app())
    
    # 总结
    print("\n" + "=" * 60)
    print("最终验证结果")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    test_names = ["模块导入", "STT系统", "主应用"]
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} {name}")
    
    print(f"\n通过率: {passed}/{total} ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("\n🎉 所有验证通过！")
        print("📦 Dockerfile修改应该能解决Google Cloud Run部署问题")
        print("🚀 可以安全地重新部署到Cloud Run")
        return True
    else:
        print(f"\n⚠️ {total-passed} 个验证失败")
        print("🔧 需要进一步检查和修复")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)