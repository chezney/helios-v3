"""
Helios Trading System V3.0 - Module Testing Framework
Test modules before deployment
Following MODULAR_ARCHITECTURE_GUIDE.md specification
"""

import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from src.utils.logger import get_logger

logger = get_logger(__name__, component="modular_architecture")


class TestStatus(str, Enum):
    """Test execution status"""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TestCase:
    """Individual test case"""
    name: str
    test_func: Callable
    timeout_seconds: int = 30
    required: bool = True  # If True, failure blocks deployment


@dataclass
class TestResult:
    """Test execution result"""
    test_name: str
    status: TestStatus
    duration_ms: float
    error: Optional[str] = None
    output: Optional[Any] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class TestSuiteResult:
    """Test suite execution result"""
    module_name: str
    total_tests: int
    passed: int
    failed: int
    skipped: int
    duration_ms: float
    results: List[TestResult] = field(default_factory=list)
    all_passed: bool = False
    timestamp: datetime = field(default_factory=datetime.utcnow)


class ModuleTester:
    """
    Module testing framework for pre-deployment validation.

    Provides:
    - Unit test execution
    - Integration test execution
    - Performance benchmarking
    - Rollback decision making
    """

    def __init__(self, module_name: str):
        self.module_name = module_name
        self.test_cases: List[TestCase] = []

    def add_test(
        self,
        name: str,
        test_func: Callable,
        timeout_seconds: int = 30,
        required: bool = True
    ) -> None:
        """
        Add a test case to the suite.

        Args:
            name: Test name
            test_func: Async test function
            timeout_seconds: Test timeout
            required: Whether test failure blocks deployment
        """
        test_case = TestCase(
            name=name,
            test_func=test_func,
            timeout_seconds=timeout_seconds,
            required=required
        )
        self.test_cases.append(test_case)
        logger.info(f"Test added to {self.module_name}: {name} (required={required})")

    async def run_tests(self, module_instance: Any) -> TestSuiteResult:
        """
        Run all tests for a module.

        Args:
            module_instance: Module instance to test

        Returns:
            Test suite result
        """
        logger.info(f"Running test suite for module: {self.module_name} ({len(self.test_cases)} tests)")

        start_time = asyncio.get_event_loop().time()
        results: List[TestResult] = []
        passed = 0
        failed = 0
        skipped = 0

        for test_case in self.test_cases:
            result = await self._run_single_test(test_case, module_instance)
            results.append(result)

            if result.status == TestStatus.PASSED:
                passed += 1
            elif result.status == TestStatus.FAILED:
                failed += 1
            elif result.status == TestStatus.SKIPPED:
                skipped += 1

        end_time = asyncio.get_event_loop().time()
        duration_ms = (end_time - start_time) * 1000

        # Determine if all required tests passed
        all_passed = all(
            r.status == TestStatus.PASSED
            for r, tc in zip(results, self.test_cases)
            if tc.required
        )

        suite_result = TestSuiteResult(
            module_name=self.module_name,
            total_tests=len(self.test_cases),
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_ms=duration_ms,
            results=results,
            all_passed=all_passed
        )

        logger.info(
            f"Test suite completed for {self.module_name}: "
            f"{passed} passed, {failed} failed, {skipped} skipped "
            f"({duration_ms:.2f}ms)"
        )

        return suite_result

    async def _run_single_test(
        self,
        test_case: TestCase,
        module_instance: Any
    ) -> TestResult:
        """Run a single test case"""
        logger.info(f"Running test: {self.module_name}.{test_case.name}")

        start_time = asyncio.get_event_loop().time()

        try:
            # Run test with timeout
            if asyncio.iscoroutinefunction(test_case.test_func):
                output = await asyncio.wait_for(
                    test_case.test_func(module_instance),
                    timeout=test_case.timeout_seconds
                )
            else:
                output = test_case.test_func(module_instance)

            end_time = asyncio.get_event_loop().time()
            duration_ms = (end_time - start_time) * 1000

            logger.info(f"✓ Test passed: {test_case.name} ({duration_ms:.2f}ms)")

            return TestResult(
                test_name=test_case.name,
                status=TestStatus.PASSED,
                duration_ms=duration_ms,
                output=output
            )

        except asyncio.TimeoutError:
            end_time = asyncio.get_event_loop().time()
            duration_ms = (end_time - start_time) * 1000

            error_msg = f"Test timed out after {test_case.timeout_seconds}s"
            logger.error(f"✗ Test failed: {test_case.name} - {error_msg}")

            return TestResult(
                test_name=test_case.name,
                status=TestStatus.FAILED,
                duration_ms=duration_ms,
                error=error_msg
            )

        except Exception as e:
            end_time = asyncio.get_event_loop().time()
            duration_ms = (end_time - start_time) * 1000

            error_msg = f"{type(e).__name__}: {str(e)}"
            logger.error(f"✗ Test failed: {test_case.name} - {error_msg}", exc_info=True)

            return TestResult(
                test_name=test_case.name,
                status=TestStatus.FAILED,
                duration_ms=duration_ms,
                error=error_msg
            )


class ModuleTestingManager:
    """
    Manage testing for all modules.

    Provides centralized test management and pre-deployment validation.
    """

    def __init__(self):
        self._testers: Dict[str, ModuleTester] = {}
        self._test_results: Dict[str, List[TestSuiteResult]] = {}

    def create_tester(self, module_name: str, category: str = "general") -> ModuleTester:
        """
        Create a test suite for a module.

        Args:
            module_name: Module name
            category: Module category (e.g., 'ml', 'trading', 'risk')

        Returns:
            Module tester instance
        """
        tester = ModuleTester(module_name)
        self._testers[module_name] = tester

        # Add category-specific default tests
        self._add_default_tests(tester, category)

        logger.info(f"Module tester created: {module_name} (category={category})")
        return tester

    def _add_default_tests(self, tester: ModuleTester, category: str) -> None:
        """Add default tests based on module category"""

        # Universal tests for all modules
        async def test_module_imports(module):
            """Test that module imports successfully"""
            assert module is not None, "Module is None"
            return True

        tester.add_test("module_imports", test_module_imports, timeout_seconds=5, required=True)

        # Category-specific tests
        if category == "ml":
            async def test_model_loaded(module):
                """Test ML model is loaded"""
                assert hasattr(module, "model") or hasattr(module, "predict"), \
                    "Module missing model or predict method"
                return True

            tester.add_test("model_loaded", test_model_loaded, timeout_seconds=10, required=True)

        elif category == "trading":
            async def test_order_methods(module):
                """Test trading methods exist"""
                required_methods = ["place_order", "cancel_order", "get_positions"]
                for method in required_methods:
                    assert hasattr(module, method), f"Missing method: {method}"
                return True

            tester.add_test("order_methods", test_order_methods, timeout_seconds=5, required=True)

    def get_tester(self, module_name: str) -> Optional[ModuleTester]:
        """Get tester for a module"""
        return self._testers.get(module_name)

    async def run_tests(self, module_name: str, module_instance: Any) -> TestSuiteResult:
        """Run tests for a module"""
        if module_name not in self._testers:
            raise ValueError(f"No tester found for module {module_name}")

        tester = self._testers[module_name]
        result = await tester.run_tests(module_instance)

        # Store result
        if module_name not in self._test_results:
            self._test_results[module_name] = []
        self._test_results[module_name].append(result)

        return result

    def get_test_history(self, module_name: str) -> List[TestSuiteResult]:
        """Get test history for a module"""
        return self._test_results.get(module_name, [])

    def get_latest_result(self, module_name: str) -> Optional[TestSuiteResult]:
        """Get latest test result for a module"""
        history = self.get_test_history(module_name)
        return history[-1] if history else None

    def get_all_results(self) -> Dict[str, TestSuiteResult]:
        """Get latest results for all modules"""
        return {
            name: self.get_latest_result(name)
            for name in self._testers.keys()
        }


# Global module testing manager instance
module_testing_manager = ModuleTestingManager()
