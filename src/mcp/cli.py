"""
MCP Tool Generator CLI

Command-line interface for managing MCP tools.
Phase 4, Task 4.7: MCP CLI
"""

import sys
import argparse
from pathlib import Path
from typing import Optional

from src.mcp.validator import load_tool_spec, save_tool_spec
from src.mcp.generator import ToolGenerator
from src.mcp.registry import tool_registry


def cmd_generate(args):
    """Generate tool from spec file."""
    spec_path = Path(args.spec_file)
    
    if not spec_path.exists():
        print(f"❌ Error: Spec file not found: {spec_path}")
        return 1
    
    try:
        # Load and validate spec
        print(f"📋 Loading spec: {spec_path}")
        spec = load_tool_spec(spec_path)
        print(f"✓ Validated spec: {spec.tool_id} v{spec.version}")
        
        # Generate code
        output_dir = Path(args.output_dir or "src/mcp/tools")
        generator = ToolGenerator(output_dir)
        
        print(f"🔨 Generating code...")
        tool_path = generator.generate(spec)
        print(f"✓ Generated tool: {tool_path}")
        
        # Generate tests
        test_path = output_dir.parent.parent / "tests" / "mcp" / f"test_{spec.tool_id}.py"
        print(f"✓ Generated tests: {test_path}")
        
        # Register tool
        if not args.no_register:
            print(f"📝 Registering tool...")
            spec_hash = generator._calculate_spec_hash(spec)
            
            tool_registry.register(
                tool_id=spec.tool_id,
                version=spec.version,
                spec_hash=spec_hash,
                module_path=f"src.mcp.tools.{spec.tool_id}",
                safety_config=spec.safety.model_dump(),
                permissions=spec.permissions,
                metadata=spec.metadata.model_dump()
            )
            print(f"✓ Registered tool: {spec.tool_id} (hash={spec_hash})")
        
        print(f"\n✅ Tool generation complete!")
        print(f"\nNext steps:")
        print(f"  1. Review generated code: {tool_path}")
        print(f"  2. Run tests: pytest {test_path}")
        print(f"  3. Import and use: from {output_dir.name}.{spec.tool_id} import {spec.name}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_validate(args):
    """Validate tool spec file(s)."""
    spec_files = args.spec_files
    
    if not spec_files:
        # Validate all specs in default directory
        spec_dir = Path("src/mcp/specs")
        spec_files = list(spec_dir.glob("*.yaml"))
    
    errors = 0
    for spec_file in spec_files:
        spec_path = Path(spec_file)
        
        try:
            spec = load_tool_spec(spec_path)
            print(f"✓ {spec_path.name}: {spec.tool_id} v{spec.version}")
        except Exception as e:
            print(f"❌ {spec_path.name}: {e}")
            errors += 1
    
    if errors == 0:
        print(f"\n✅ All specs valid ({len(spec_files)} files)")
        return 0
    else:
        print(f"\n❌ {errors} spec(s) failed validation")
        return 1


def cmd_list(args):
    """List registered tools."""
    status = args.status or "active"
    
    try:
        tools = tool_registry.list_tools(status=status, limit=args.limit)
        
        if not tools:
            print(f"No {status} tools found")
            return 0
        
        print(f"\n{status.upper()} TOOLS ({len(tools)}):\n")
        print(f"{'Tool ID':<30} {'Version':<10} {'Permissions':<30} {'Created'}")
        print("-" * 90)
        
        for tool in tools:
            tool_id = tool["tool_id"]
            version = tool["version"]
            perms = ", ".join(tool["permissions"][:2])
            if len(tool["permissions"]) > 2:
                perms += f" +{len(tool['permissions']) - 2}"
            created = tool.get("created_at", "N/A")
            
            print(f"{tool_id:<30} {version:<10} {perms:<30} {created}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_delete(args):
    """Delete (soft delete) a tool."""
    tool_id = args.tool_id
    
    try:
        # Check if tool exists
        tool = tool_registry.get_tool(tool_id)
        if not tool:
            print(f"❌ Tool not found: {tool_id}")
            return 1
        
        # Confirm deletion
        if not args.force:
            response = input(f"Delete tool '{tool_id}'? (y/N): ")
            if response.lower() != 'y':
                print("Cancelled")
                return 0
        
        # Delete tool
        tool_registry.delete_tool(tool_id)
        print(f"✓ Deleted tool: {tool_id}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_info(args):
    """Show tool information."""
    tool_id = args.tool_id
    
    try:
        tool = tool_registry.get_tool(tool_id)
        
        if not tool:
            print(f"❌ Tool not found: {tool_id}")
            return 1
        
        print(f"\nTOOL: {tool_id}")
        print("=" * 60)
        print(f"Version:      {tool['version']}")
        print(f"Status:       {tool['status']}")
        print(f"Spec Hash:    {tool['spec_hash']}")
        print(f"Module Path:  {tool['module_path']}")
        print(f"\nPermissions:")
        for perm in tool['permissions']:
            print(f"  - {perm}")
        
        print(f"\nSafety Config:")
        safety = tool['safety_config']
        if safety.get('deny_keywords'):
            print(f"  Denied keywords: {len(safety['deny_keywords'])}")
        if safety.get('allowed_datasets'):
            print(f"  Allowed datasets: {', '.join(safety['allowed_datasets'])}")
        print(f"  Max rows: {safety.get('max_rows_returned', 'N/A')}")
        print(f"  Timeout: {safety.get('timeout_seconds', 'N/A')}s")
        
        print(f"\nMetadata:")
        metadata = tool.get('metadata', {})
        print(f"  Author: {metadata.get('author', 'N/A')}")
        print(f"  Tags: {', '.join(metadata.get('tags', []))}")
        print(f"  Cost estimate: ${metadata.get('cost_estimate_usd', 0):.6f}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def cmd_stats(args):
    """Show registry statistics."""
    try:
        stats = tool_registry.get_stats()
        
        print("\nREGISTRY STATISTICS")
        print("=" * 60)
        print(f"Total tools: {stats['total_tools']}")
        print(f"Cached tools: {stats['total_cached']}")
        
        print(f"\nBy Status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")
        
        print(f"\nBy Permission:")
        for prefix, count in sorted(stats['by_permission'].items()):
            print(f"  {prefix}.*: {count}")
        
        return 0
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MCP Tool Generator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate tool from spec
  python -m src.mcp.cli generate src/mcp/specs/bq_query_readonly.yaml
  
  # Validate all specs
  python -m src.mcp.cli validate
  
  # List active tools
  python -m src.mcp.cli list
  
  # Show tool info
  python -m src.mcp.cli info bq_query_readonly
  
  # Delete tool
  python -m src.mcp.cli delete bq_query_readonly --force
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Generate command
    gen_parser = subparsers.add_parser("generate", help="Generate tool from spec")
    gen_parser.add_argument("spec_file", help="Path to YAML spec file")
    gen_parser.add_argument("-o", "--output-dir", help="Output directory for generated code")
    gen_parser.add_argument("--no-register", action="store_true", help="Don't register tool")
    gen_parser.set_defaults(func=cmd_generate)
    
    # Validate command
    val_parser = subparsers.add_parser("validate", help="Validate spec file(s)")
    val_parser.add_argument("spec_files", nargs="*", help="Spec files to validate")
    val_parser.set_defaults(func=cmd_validate)
    
    # List command
    list_parser = subparsers.add_parser("list", help="List registered tools")
    list_parser.add_argument("-s", "--status", help="Filter by status", default="active")
    list_parser.add_argument("-l", "--limit", type=int, default=100, help="Max results")
    list_parser.set_defaults(func=cmd_list)
    
    # Delete command
    del_parser = subparsers.add_parser("delete", help="Delete a tool")
    del_parser.add_argument("tool_id", help="Tool ID to delete")
    del_parser.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    del_parser.set_defaults(func=cmd_delete)
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show tool information")
    info_parser.add_argument("tool_id", help="Tool ID")
    info_parser.set_defaults(func=cmd_info)
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show registry statistics")
    stats_parser.set_defaults(func=cmd_stats)
    
    # Parse args
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Execute command
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
