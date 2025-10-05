"""
Example: Modular Deployment Workflow
Demonstrates how to use Helios V3.0's modular architecture for safe deployments
"""

import asyncio
from src.core import (
    module_loader,
    feature_flags,
    circuit_breaker_manager,
    module_testing_manager,
    RolloutStrategy
)
from src.utils.logger import get_logger

logger = get_logger(__name__, component="modular_deployment_example")


async def example_deploy_new_module():
    """
    Example: Deploy a new version of a module with gradual rollout
    """
    logger.info("=" * 80)
    logger.info("EXAMPLE: Modular Deployment Workflow")
    logger.info("=" * 80)

    # Initialize feature flags
    await feature_flags.initialize()
    logger.info("✅ Feature flags initialized")

    # Step 1: Register the new module
    logger.info("\n📦 Step 1: Register new module version...")
    await module_loader.register_module(
        name="example_predictor_v2",
        module_path="src.ml.inference.predictor",  # Example path
        version="2.0.0",
        dependencies=[],
        hot_reloadable=True
    )
    logger.info("✅ Module registered: example_predictor_v2 v2.0.0")

    # Step 2: Load the module
    logger.info("\n🔄 Step 2: Load the module...")
    try:
        instance = await module_loader.load_module("example_predictor_v2")
        logger.info(f"✅ Module loaded successfully: {type(instance)}")
    except Exception as e:
        logger.error(f"❌ Failed to load module: {e}")
        return

    # Step 3: Test the module
    logger.info("\n🧪 Step 3: Test the module...")
    tester = module_testing_manager.create_tester("example_predictor_v2", "ml")

    # Add custom test
    async def test_basic_prediction(instance):
        """Test that predictor can make basic predictions"""
        logger.info("   Running basic prediction test...")
        return True  # In real scenario, call instance.predict()

    tester.add_test(
        "basic_prediction",
        test_basic_prediction,
        required=True,
        timeout=10.0,
        description="Test basic prediction functionality"
    )

    # Run tests
    all_passed = await tester.run_tests(instance)
    report = tester.get_test_report()

    logger.info(f"   Tests: {report['results']['passed']} passed, {report['results']['failed']} failed")

    if not all_passed:
        logger.error("❌ Tests failed, aborting deployment")
        return

    logger.info("✅ All tests passed")

    # Step 4: Create feature flag for gradual rollout
    logger.info("\n🚩 Step 4: Create feature flag...")
    await feature_flags.create_flag(
        "predictor_v2",
        enabled=False,
        strategy=RolloutStrategy.PERCENTAGE,
        description="New predictor version 2.0"
    )
    logger.info("✅ Feature flag created: predictor_v2")

    # Step 5: Enable for 10% of traffic
    logger.info("\n📊 Step 5: Enable for 10% of traffic...")
    await feature_flags.enable_flag("predictor_v2", RolloutStrategy.PERCENTAGE)
    await feature_flags.set_percentage("predictor_v2", 10.0)
    logger.info("✅ Enabled for 10% of traffic")

    # Step 6: Create circuit breaker for safety
    logger.info("\n🔌 Step 6: Create circuit breaker...")
    breaker = await circuit_breaker_manager.get_or_create("example_predictor")
    logger.info(f"✅ Circuit breaker created: {breaker.name}")

    # Step 7: Simulate gradual rollout
    logger.info("\n🚀 Step 7: Gradual rollout...")
    rollout_percentages = [10.0, 25.0, 50.0, 100.0]

    for percentage in rollout_percentages:
        logger.info(f"   → Setting rollout to {percentage}%...")
        await feature_flags.set_percentage("predictor_v2", percentage)
        await asyncio.sleep(1)  # In production, wait hours/days between increases

        # Check circuit breaker status
        status = breaker.get_status()
        logger.info(f"   Circuit breaker state: {status['state']}")

        if status['state'] == 'open':
            logger.error("   ⚠️ Circuit breaker opened, halting rollout!")
            break

    # Step 8: Full rollout
    if breaker.state.value == "closed":
        logger.info("\n🎉 Step 8: Full rollout (100%)...")
        await feature_flags.enable_flag("predictor_v2", RolloutStrategy.ALL_ON)
        logger.info("✅ Feature fully deployed to all traffic")

    # Step 9: Show final status
    logger.info("\n📋 Final Status:")
    module_status = module_loader.get_module_status("example_predictor_v2")
    logger.info(f"   Module: {module_status['name']} - {module_status['state']}")

    flags = feature_flags.get_all_flags()
    logger.info(f"   Feature Flag: predictor_v2 - Enabled: {flags['predictor_v2']['enabled']}")

    breaker_status = breaker.get_status()
    logger.info(f"   Circuit Breaker: {breaker_status['state']} - Success Rate: {breaker_status['metrics']['success_rate']:.1f}%")

    logger.info("\n" + "=" * 80)
    logger.info("✅ DEPLOYMENT COMPLETE")
    logger.info("=" * 80)


async def example_hot_swap():
    """
    Example: Hot-swap a module while system is running
    """
    logger.info("\n" + "=" * 80)
    logger.info("EXAMPLE: Hot-Swap Module")
    logger.info("=" * 80)

    # Register original module
    logger.info("\n📦 Registering original module...")
    await module_loader.register_module(
        name="trading_engine",
        module_path="src.trading.execution.execution_engine",
        version="1.0.0",
        hot_reloadable=True
    )

    # Load original
    logger.info("🔄 Loading original version...")
    await module_loader.load_module("trading_engine")
    logger.info("✅ Original module loaded")

    # Simulate hot-swap to new version
    logger.info("\n🔥 Hot-swapping to new version...")
    success = await module_loader.swap_module(
        "trading_engine",
        new_version_path="src.trading.execution.execution_engine"  # In real scenario, this would be v2
    )

    if success:
        logger.info("✅ Hot-swap successful!")
        status = module_loader.get_module_status("trading_engine")
        logger.info(f"   New state: {status['state']}")
        logger.info(f"   Load time: {status['load_time']}")
    else:
        logger.error("❌ Hot-swap failed, rolled back to original")


async def example_feature_flag_usage():
    """
    Example: Use feature flags in application code
    """
    logger.info("\n" + "=" * 80)
    logger.info("EXAMPLE: Feature Flag Usage in Code")
    logger.info("=" * 80)

    await feature_flags.initialize()

    # Example: Check if feature is enabled
    logger.info("\n🔍 Checking feature flags...")

    if await feature_flags.is_enabled("neural_network_v2"):
        logger.info("✅ Using Neural Network V2")
        # Use new version
    else:
        logger.info("📦 Using Neural Network V1 (legacy)")
        # Use legacy version

    # Example: Context-based evaluation
    context = {"session_id": "user_12345"}

    if await feature_flags.is_enabled("websocket_v2", context):
        logger.info("✅ Using WebSocket V2 for this session")
    else:
        logger.info("📦 Using WebSocket V1 for this session")

    # Show all flags
    logger.info("\n📋 All Feature Flags:")
    all_flags = feature_flags.get_all_flags()
    for flag_name, flag_data in all_flags.items():
        status = "🟢 ON" if flag_data["enabled"] else "🔴 OFF"
        logger.info(f"   {status} {flag_name}: {flag_data['description']}")


async def example_circuit_breaker():
    """
    Example: Use circuit breaker to protect critical operations
    """
    logger.info("\n" + "=" * 80)
    logger.info("EXAMPLE: Circuit Breaker Protection")
    logger.info("=" * 80)

    # Create circuit breaker
    breaker = await circuit_breaker_manager.get_or_create("external_api")
    logger.info(f"✅ Circuit breaker created: {breaker.name}")

    # Example protected function
    async def risky_operation():
        """Simulate external API call"""
        import random
        if random.random() < 0.3:  # 30% failure rate
            raise Exception("API timeout")
        return {"data": "success"}

    # Execute with protection
    logger.info("\n🔌 Executing protected operations...")

    for i in range(10):
        try:
            result = await breaker.call(risky_operation)
            logger.info(f"   Request {i+1}: ✅ Success - {result}")
        except Exception as e:
            logger.error(f"   Request {i+1}: ❌ Failed - {e}")

        await asyncio.sleep(0.1)

    # Show final status
    status = breaker.get_status()
    logger.info(f"\n📊 Circuit Breaker Status:")
    logger.info(f"   State: {status['state']}")
    logger.info(f"   Total Requests: {status['metrics']['total_requests']}")
    logger.info(f"   Success Rate: {status['metrics']['success_rate']:.1f}%")
    logger.info(f"   Rejected Requests: {status['metrics']['rejected_requests']}")


async def main():
    """Run all examples"""
    logger.info("\n" + "🚀" * 40)
    logger.info("HELIOS V3.0 - MODULAR ARCHITECTURE EXAMPLES")
    logger.info("🚀" * 40 + "\n")

    try:
        # Example 1: Full deployment workflow
        await example_deploy_new_module()

        # Example 2: Hot-swap
        await example_hot_swap()

        # Example 3: Feature flags in code
        await example_feature_flag_usage()

        # Example 4: Circuit breakers
        await example_circuit_breaker()

        logger.info("\n" + "✅" * 40)
        logger.info("ALL EXAMPLES COMPLETED SUCCESSFULLY")
        logger.info("✅" * 40 + "\n")

    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
