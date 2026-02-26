import os
import json
import datetime
from typing import Any, Dict, List, Tuple
from astrbot.api.star import Context, StarTools
from astrbot.api import logger
from .utils import CommandUtils


class DataManager:
    def __init__(self, context: Context, config):
        self.context = context
        self.config = config

        # 旧版 JSON 存储路径（用于自动迁移）
        plugin_data_dir = StarTools.get_data_dir("command_to_llm")
        self.legacy_data_file = plugin_data_dir / "command_mappings.json"

        self.command_mappings: Dict[str, Dict] = {}
        self._ensure_config_defaults()
        self.reload_from_config()
        self._migrate_legacy_data_if_needed()

    def _save_config(self):
        """保存配置到 AstrBot 官方配置存储"""
        try:
            if hasattr(self.config, "save_config"):
                self.config.save_config()
        except Exception as e:
            logger.error(f"保存插件配置失败: {e}")

    def _get_section(
        self, section_name: str, default_value: Dict[str, Any]
    ) -> Dict[str, Any]:
        section = self.config.get(section_name)
        if isinstance(section, dict):
            return section

        new_section = default_value.copy()
        self.config[section_name] = new_section
        return new_section

    def _ensure_config_defaults(self):
        """确保配置结构完整，兼容旧版本与手动编辑场景"""
        basic_config = self._get_section(
            "basic_config",
            {
                "enable_plugin": True,
                "auto_refresh_on_change": True,
                "strict_validation": False,
            },
        )
        basic_config.setdefault("enable_plugin", True)
        basic_config.setdefault("auto_refresh_on_change", True)
        basic_config.setdefault("strict_validation", False)

        mapping_config = self._get_section(
            "mapping_config",
            {
                "command_mappings": [],
                "allow_duplicate_llm_function": True,
            },
        )
        if not isinstance(mapping_config.get("command_mappings"), list):
            mapping_config["command_mappings"] = []
        mapping_config.setdefault("allow_duplicate_llm_function", True)

        execution_config = self._get_section(
            "execution_config",
            {
                "capture_timeout_sec": 20,
                "forward_interval_sec": 0.5,
                "response_mode": "forward_only",
            },
        )
        execution_config.setdefault("capture_timeout_sec", 20)
        execution_config.setdefault("forward_interval_sec", 0.5)
        execution_config.setdefault("response_mode", "forward_only")

        compat_config = self._get_section(
            "compat_config",
            {
                "auto_migrate_legacy_json": True,
                "keep_legacy_backup": True,
                "migration_once_flag": False,
            },
        )
        compat_config.setdefault("auto_migrate_legacy_json", True)
        compat_config.setdefault("keep_legacy_backup", True)
        compat_config.setdefault("migration_once_flag", False)

        tool_config = self._get_section(
            "tool_config",
            {
                "tool_description": "将已有指令映射为可调用函数，让 AI 能触发插件命令。",
                "arg_description": "指令参数字符串。推荐 key=value 格式，多参数用空格分隔。例如：text=喝水 time=10:00。",
            },
        )
        tool_config.setdefault(
            "tool_description", "将已有指令映射为可调用函数，让 AI 能触发插件命令。"
        )
        tool_config.setdefault(
            "arg_description",
            "指令参数字符串。推荐 key=value 格式，多参数用空格分隔。例如：text=喝水 time=10:00。",
        )

        self.config["basic_config"] = basic_config
        self.config["mapping_config"] = mapping_config
        self.config["execution_config"] = execution_config
        self.config["tool_config"] = tool_config
        self.config["compat_config"] = compat_config
        self._save_config()

    def _normalize_mapping_entries(
        self, entries: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        normalized: Dict[str, Dict[str, Any]] = {}
        for item in entries:
            if not isinstance(item, dict):
                continue
            command_name = str(item.get("command_name", "")).strip()
            llm_function = str(item.get("llm_function", "")).strip()
            if not command_name or not llm_function:
                continue

            aliases = item.get("aliases", [])
            if not isinstance(aliases, list):
                aliases = []

            normalized[command_name] = {
                "llm_function": llm_function,
                "description": str(item.get("description", "")).strip(),
                "arg_description": str(item.get("arg_description", "")).strip(),
                "enabled": bool(item.get("enabled", True)),
                "group": str(item.get("group", "default")).strip() or "default",
                "aliases": [
                    str(alias).strip() for alias in aliases if str(alias).strip()
                ],
                "created_at": str(item.get("created_at", "")).strip(),
            }
        return normalized

    def _serialize_mappings(self) -> List[Dict[str, Any]]:
        serialized: List[Dict[str, Any]] = []
        for command_name, mapping in self.command_mappings.items():
            serialized.append(
                {
                    "__template_key": "mapping_item",
                    "enabled": bool(mapping.get("enabled", True)),
                    "command_name": command_name,
                    "llm_function": str(mapping.get("llm_function", "")),
                    "description": str(mapping.get("description", "")),
                    "arg_description": str(mapping.get("arg_description", "")),
                    "group": str(mapping.get("group", "default")) or "default",
                    "aliases": list(mapping.get("aliases", [])),
                    "created_at": str(mapping.get("created_at", "")),
                }
            )
        return serialized

    def _save_mappings_to_config(self):
        mapping_config = self._get_section("mapping_config", {"command_mappings": []})
        mapping_config["command_mappings"] = self._serialize_mappings()
        self.config["mapping_config"] = mapping_config
        self._save_config()

    def reload_from_config(self):
        """从配置重新加载指令映射到内存缓存"""
        self._ensure_config_defaults()
        mapping_config = self._get_section("mapping_config", {"command_mappings": []})
        raw_entries = mapping_config.get("command_mappings", [])
        if not isinstance(raw_entries, list):
            raw_entries = []
        self.command_mappings = self._normalize_mapping_entries(raw_entries)

    def _load_legacy_mappings(self) -> Dict[str, Dict[str, Any]]:
        if not os.path.exists(self.legacy_data_file):
            return {}

        try:
            with open(self.legacy_data_file, "r", encoding="utf-8") as f:
                legacy_data = json.load(f)
        except Exception as e:
            logger.error(f"读取旧版指令映射失败: {e}")
            return {}

        if not isinstance(legacy_data, dict):
            return {}

        migrated: Dict[str, Dict[str, Any]] = {}
        for command_name, mapping in legacy_data.items():
            if not isinstance(mapping, dict):
                continue
            llm_function = str(mapping.get("llm_function", "")).strip()
            if not llm_function:
                continue
            migrated[str(command_name).strip()] = {
                "llm_function": llm_function,
                "description": str(mapping.get("description", "")).strip(),
                "arg_description": "",
                "enabled": True,
                "group": "legacy",
                "aliases": [],
                "created_at": str(mapping.get("created_at", "")).strip()
                or str(datetime.datetime.now()),
            }
        return migrated

    def _migrate_legacy_data_if_needed(self):
        compat_config = self._get_section("compat_config", {})
        auto_migrate = bool(compat_config.get("auto_migrate_legacy_json", True))
        already_migrated = bool(compat_config.get("migration_once_flag", False))
        keep_backup = bool(compat_config.get("keep_legacy_backup", True))

        if not auto_migrate or already_migrated:
            return

        if self.command_mappings:
            compat_config["migration_once_flag"] = True
            self.config["compat_config"] = compat_config
            self._save_config()
            return

        legacy_mappings = self._load_legacy_mappings()
        if not legacy_mappings:
            compat_config["migration_once_flag"] = True
            self.config["compat_config"] = compat_config
            self._save_config()
            return

        self.command_mappings = legacy_mappings
        self._save_mappings_to_config()
        logger.info(
            f"已从旧版 JSON 自动迁移 {len(legacy_mappings)} 条指令映射到插件配置"
        )

        if keep_backup and os.path.exists(self.legacy_data_file):
            backup_path = self.legacy_data_file.with_suffix(".json.bak")
            try:
                os.replace(self.legacy_data_file, backup_path)
                logger.info(f"旧版映射文件已备份到: {backup_path}")
            except Exception as e:
                logger.error(f"备份旧版映射文件失败: {e}")

        compat_config["migration_once_flag"] = True
        self.config["compat_config"] = compat_config
        self._save_config()

    def is_plugin_enabled(self) -> bool:
        basic_config = self._get_section("basic_config", {})
        return bool(basic_config.get("enable_plugin", True))

    def should_auto_refresh_on_change(self) -> bool:
        basic_config = self._get_section("basic_config", {})
        return bool(basic_config.get("auto_refresh_on_change", True))

    def strict_validation_enabled(self) -> bool:
        basic_config = self._get_section("basic_config", {})
        return bool(basic_config.get("strict_validation", False))

    def allow_duplicate_llm_function(self) -> bool:
        mapping_config = self._get_section("mapping_config", {})
        return bool(mapping_config.get("allow_duplicate_llm_function", True))

    def get_capture_timeout(self) -> float:
        execution_config = self._get_section("execution_config", {})
        try:
            return max(float(execution_config.get("capture_timeout_sec", 20)), 1.0)
        except Exception:
            return 20.0

    def get_forward_interval(self) -> float:
        execution_config = self._get_section("execution_config", {})
        try:
            return max(float(execution_config.get("forward_interval_sec", 0.5)), 0.0)
        except Exception:
            return 0.5

    def get_response_mode(self) -> str:
        execution_config = self._get_section("execution_config", {})
        mode = str(execution_config.get("response_mode", "forward_only"))
        if mode not in {"forward_and_text", "text_only", "forward_only"}:
            return "forward_only"
        return mode

    def get_tool_description(self) -> str:
        tool_config = self._get_section("tool_config", {})
        return str(
            tool_config.get(
                "tool_description", "将已有指令映射为可调用函数，让 AI 能触发插件命令。"
            )
        ).strip()

    def get_default_arg_description(self) -> str:
        tool_config = self._get_section("tool_config", {})
        return str(
            tool_config.get(
                "arg_description",
                "指令参数字符串。推荐 key=value 格式，多参数用空格分隔。例如：text=喝水 time=10:00。",
            )
        ).strip()

    def add_mapping(
        self, command_name: str, llm_function: str, description: str = ""
    ) -> Tuple[bool, str]:
        """添加指令映射

        Returns:
            (success, message): 成功状态和消息
        """
        self.reload_from_config()
        logger.info(
            f"[data_manager] add_mapping 被调用 - 指令: '{command_name}', 函数: '{llm_function}', 描述: '{description}'"
        )

        # 验证参数
        errors = CommandUtils.validate_mapping(command_name, llm_function)
        if errors:
            logger.warning(f"[data_manager] 参数验证失败: {errors}")
            return False, f"参数验证失败: {'; '.join(errors)}"

        if self.strict_validation_enabled():
            if not llm_function.replace("_", "").isalnum():
                return False, "LLM函数名称仅允许字母、数字和下划线"

        if not self.allow_duplicate_llm_function():
            for existed_command, mapping in self.command_mappings.items():
                if existed_command == command_name:
                    continue
                if mapping.get("llm_function") == llm_function:
                    return (
                        False,
                        f"LLM函数 '{llm_function}' 已被指令 '{existed_command}' 使用",
                    )

        if command_name in self.command_mappings:
            logger.warning(f"[data_manager] 指令已存在: {command_name}")
            return False, f"指令 '{command_name}' 已存在映射"

        logger.info(f"[data_manager] 开始添加映射")
        self.command_mappings[command_name] = {
            "llm_function": llm_function,
            "description": description,
            "enabled": True,
            "group": "default",
            "aliases": [],
            "created_at": str(datetime.datetime.now()),
        }

        logger.info(f"[data_manager] 保存映射配置")
        self._save_mappings_to_config()
        logger.info(f"[data_manager] 映射添加完成")
        return True, f"成功添加指令映射：'{command_name}' -> '{llm_function}'"

    def remove_mapping(self, command_name: str) -> bool:
        """删除指令映射"""
        self.reload_from_config()
        if command_name not in self.command_mappings:
            return False

        del self.command_mappings[command_name]
        self._save_mappings_to_config()
        return True

    def set_mapping_enabled(self, command_name: str, enabled: bool) -> Tuple[bool, str]:
        """启用/禁用映射"""
        self.reload_from_config()
        mapping = self.command_mappings.get(command_name)
        if not mapping:
            return False, f"错误：指令 '{command_name}' 不存在映射"

        current_state = bool(mapping.get("enabled", True))
        if current_state == enabled:
            state_text = "启用" if enabled else "禁用"
            return False, f"指令 '{command_name}' 已是{state_text}状态"

        mapping["enabled"] = enabled
        self.command_mappings[command_name] = mapping
        self._save_mappings_to_config()

        state_text = "启用" if enabled else "禁用"
        return True, f"已{state_text}指令映射：'{command_name}'"

    def get_mapping(self, command_name: str, enabled_only: bool = True) -> Dict:
        """获取指令映射"""
        self.reload_from_config()
        mapping = self.command_mappings.get(command_name, {})
        if enabled_only and mapping and not mapping.get("enabled", True):
            return {}
        return mapping.copy() if mapping else {}

    def list_mappings(
        self, enabled_only: bool = False, state_filter: str = "all"
    ) -> Dict[str, Dict]:
        """列出指令映射

        Args:
            enabled_only: 兼容旧参数，等价于 state_filter="enabled"
            state_filter: all/enabled/disabled
        """
        self.reload_from_config()
        mode = state_filter.lower().strip()
        if enabled_only and mode == "all":
            mode = "enabled"

        if mode == "all":
            return self.command_mappings.copy()
        if mode == "enabled":
            return {
                command_name: mapping
                for command_name, mapping in self.command_mappings.items()
                if mapping.get("enabled", True)
            }
        if mode == "disabled":
            return {
                command_name: mapping
                for command_name, mapping in self.command_mappings.items()
                if not mapping.get("enabled", True)
            }
        return self.command_mappings.copy()
