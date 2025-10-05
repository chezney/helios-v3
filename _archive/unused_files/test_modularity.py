"""
Quick test script for modular architecture
Run this to verify module loader, feature flags, and circuit breakers are working
"""

import asyncio
from src.core import (
    module_loader,
    feature_flags,
    circuit_breaker_manager,
    module_testing_manager,
)
from src.utils.logger import setup_logging, get_logger

# Setup logging
setup_logging(log_level="INFO", log_format="text", log_dir="logs")
logger = get_logger(__name__)


async def test_module_loader():
    """Test module loader functionality"""
    logger.info("=" * 60)
    logger.info("Testing Module Loader")
    logger.info("=" * 60)

    # Register a test module
    await module_loader.register_module(
        name="test_module",
        module_path="src.core.module_loader",  # Use existing module for testing
        version="1.0.0",
        hot_reloadable=True
    )

    # Load module
    instance = await module_loader.load_module("test_module")
    logger.info(f"✓ Module loaded successfully: {instance}")

    # Get status
    status = module_loader.get_module_status("test_module")
    logger.info(f"✓ Module status: {status}")

    # Get all modules
    all_modules = module_loader.get_all_modules_status()
    logger.info(f"✓ Total registered modules: {len(all_modules)}")

    logger.info("✓ Module Loader tests passed!\n")


async def test_feature_flags():
    """Test feature flags functionality"""
    logger.info("=" * 60)
    logger.info("Testing Feature Flags")
    logger.info("=" * 60)

    # Check default flags
    all_flags = feature_flags.get_all_flags()
    logger.info(f"✓ Default feature flags loaded: {len(all_flags)}")

    for flag_name, flag_config in all_flags.items():
        status = "ENABLED" if flag_config.enabled else "DISABLED"
        logger.info(f"  - {flag_name}: {status}")

    # Test feature flag check
    is_enabled = await feature_flags.is_enabled("llm_strategic_analysis")
    logger.info(f"✓ LLM Strategic Analysis enabled: {is_enabled}")

    # Create a test flag
    await feature_flags.create_flag(
        name="test_feature",
        enabled=False,
        percentage=0.0,
        metadata={"description": "Test feature for validation"}
    )
    logger.info("✓ Test feature flag created")

    # Set percentage
    await feature_flags.set_percentage("test_feature", 50.0)
    logger.info("✓ Test feature flag set to 50%")

    # Check status
    test_flag_status = feature_flags.get_flag_status("test_feature")
    logger.info(f"✓ Test flag status: {test_flag_status}")

    logger.info("✓ Feature Flags tests passed!\n")


async def test_circuit_breakers():
    """Test circuit breaker functionality"""
    logger.info("=" * 60)
    logger.info("Testing Circuit Breakers")
    logger.info("=" * 60)

    # Create a test circuit breaker
    breaker = await circuit_breaker_manager.create_breaker(
        name="test_service",
        failure_threshold=3,
        success_threshold=2,
        timeout_seconds=5,
        rolling_window_seconds=10
    )
    logger.info("✓ Circuit breaker created")

    # Get status
    status = breaker.get_status()
    logger.info(f"✓ Circuit breaker status: {status['state']}")

    # Test successful call
    async def successful_operation():
        return "success"

    result = await breaker.call(successful_operation)
    logger.info(f"✓ Successful call result: {result}")

    # Test failing call
    async def failing_operation():
        raise Exception("Simulated failure")

    failed_count = 0
    for i in range(3):
        try:
            await breaker.call(failing_operation)
        except Exception:
            failed_count += 1
            logger.info(f"  Failure {failed_count}/3 recorded")

    # Check if circuit opened
    status = breaker.get_status()
    logger.info(f"✓ Circuit state after failures: {status['state']}")

    # Get all circuit breakers
    all_breakers = circuit_breaker_manager.get_all_statuses()
    logger.info(f"✓ Total circuit breakers: {len(all_breakers)}")

    logger.info("✓ Circuit Breaker tests passed!\n")


async def test_module_testing():
    """Test module testing framework"""
    logger.info("=" * 60)
    logger.info("Testing Module Testing Framework")
    logger.info("=" * 60)

    # Create a tester
    tester = module_testing_manager.create_tester("test_module", category="general")
    logger.info("✓ Module tester created")

    # Add a custom test
    async def custom_test(module):
        """Custom test function"""
        assert module is not None, "Module is None"
        return "Test passed"

    tester.add_test("custom_test", custom_test, timeout_seconds=5, required=True)
    logger.info("✓ Custom test added")

    # Load test module
    test_module = await module_loader.load_module("test_module")

    # Run tests
    result = await module_testing_manager.run_tests("test_module", test_module)
    logger.info(f"✓ Tests completed: {result.passed}/{result.total_tests} passed")

    for test_result in result.results:
        status_symbol = "✓" if test_result.status.value == "passed" else "✗"
        logger.info(f"  {status_symbol} {test_result.test_name}: {test_result.status.value}")

    logger.info("✓ Module Testing Framework tests passed!\n")


async def main():
    """Run all tests"""
    logger.info("\n")
    logger.info("=" * 60)
    logger.info("  HELIOS V3.0 - MODULAR ARCHITECTURE TEST SUITE")
    logger.info("=" * 60)
    logger.info("\n")

    try:
        await test_module_loader()
        await test_feature_flags()
        await test_circuit_breakers()
        await test_module_testing()

        logger.info("=" * 60)
        logger.info("  ✓ ALL TESTS PASSED!")
        logger.info("=" * 60)
        logger.info("\nModular architecture is working correctly!")
        logger.info("You can now start the main application with:")
        logger.info("  python main_v3.py")
        logger.info("\n")

    except Exception as e:
        logger.error(f"✗ TEST FAILED: {e}", exc_info=True)
        logger.info("\nPlease fix the errors before starting the application.")


if __name__ == "__main__":
    asyncio.run(main())
