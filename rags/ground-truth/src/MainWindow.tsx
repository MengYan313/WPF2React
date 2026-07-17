// 主窗口组件 - 简化版
import { useState } from "react";
import {
  Box,
  Button,
  FormLabel,
  FormControlLabel,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  Typography,
  List,
  ListItem,
  ListItemText,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  MenuItem,
  Menu,
} from "@mui/material";
import { expenseData, employees, costCenters } from "./data";
import { CreateExpenseReportDialogBox } from "./CreateExpenseReportDialogBox";

/**
 * 主窗口组件
 * 简化：直接操作全局 expenseData
 */
export function MainWindow() {
  const [employeeType, setEmployeeType] = useState("FTE");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [aboutDialogOpen, setAboutDialogOpen] = useState(false);
  const [fileMenuAnchor, setFileMenuAnchor] = useState<null | HTMLElement>(null);
  const [helpMenuAnchor, setHelpMenuAnchor] = useState<null | HTMLElement>(null);

  // 直接更新全局数据，简化数据绑定
  const handleAliasChange = (value: string) => {
    expenseData.alias = value;
  };

  const handleEmployeeNumberChange = (value: string) => {
    expenseData.employeeNumber = value;
  };

  const handleCostCenterChange = (value: string) => {
    expenseData.costCenter = value;
  };

  return (
    <Box p={2}>
      <Stack spacing={2} maxWidth={600}>
        {/* 简化菜单栏 */}
        <Box borderBottom={1} borderColor="divider" pb={1}>
          <Stack direction="row" spacing={1}>
            <Button onClick={(e) => setFileMenuAnchor(e.currentTarget)}>File</Button>
            <Menu
              anchorEl={fileMenuAnchor}
              open={Boolean(fileMenuAnchor)}
              onClose={() => setFileMenuAnchor(null)}
            >
              <MenuItem
                onClick={() => {
                  setCreateDialogOpen(true);
                  setFileMenuAnchor(null);
                }}
              >
                Create Expense Report...
              </MenuItem>
              <MenuItem onClick={() => window.close()}>Exit</MenuItem>
            </Menu>
            <Button onClick={(e) => setHelpMenuAnchor(e.currentTarget)}>Help</Button>
            <Menu
              anchorEl={helpMenuAnchor}
              open={Boolean(helpMenuAnchor)}
              onClose={() => setHelpMenuAnchor(null)}
            >
              <MenuItem
                onClick={() => {
                  setAboutDialogOpen(true);
                  setHelpMenuAnchor(null);
                }}
              >
                About
              </MenuItem>
            </Menu>
          </Stack>
        </Box>

        {/* 简化表单布局 */}
        <Stack direction="row" spacing={2} alignItems="center">
          <FormLabel sx={{ minWidth: 150 }}>Email:</FormLabel>
          <TextField
            defaultValue={expenseData.alias}
            onChange={(e) => handleAliasChange(e.target.value)}
            placeholder="Enter email"
            size="small"
            sx={{ flex: 1 }}
          />
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center">
          <FormLabel sx={{ minWidth: 150 }}>Employee Number:</FormLabel>
          <TextField
            defaultValue={expenseData.employeeNumber}
            onChange={(e) => handleEmployeeNumberChange(e.target.value)}
            placeholder="Enter employee number"
            size="small"
            sx={{ flex: 1 }}
          />
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center">
          <FormLabel sx={{ minWidth: 150 }}>Cost Center:</FormLabel>
          <Select
            defaultValue={expenseData.costCenter}
            onChange={(e) => handleCostCenterChange(e.target.value)}
            size="small"
            sx={{ flex: 1 }}
          >
            {costCenters.map((cc) => (
              <MenuItem key={cc.number} value={cc.number}>
                {cc.name}
              </MenuItem>
            ))}
          </Select>
        </Stack>

        <Stack direction="row" spacing={2} alignItems="center">
          <FormLabel sx={{ minWidth: 150 }}>Employees:</FormLabel>
          <RadioGroup
            row
            value={employeeType}
            onChange={(e) => setEmployeeType(e.target.value)}
          >
            <FormControlLabel value="FTE" control={<Radio />} label="FTE" />
            <FormControlLabel value="CSG" control={<Radio />} label="CSG" />
            <FormControlLabel value="Vendor" control={<Radio />} label="Vendor" />
          </RadioGroup>
        </Stack>

        <Stack direction="row" spacing={2} alignItems="flex-start">
          <FormLabel sx={{ minWidth: 150, pt: 1 }}>Employee List:</FormLabel>
          <List sx={{ border: 1, borderColor: "divider", maxHeight: 200, overflow: "auto", flex: 1 }}>
            {employees.filter((e) => e.type === employeeType).map((emp, index) => (
              <ListItem key={index}>
                <ListItemText primary={emp.name} />
              </ListItem>
            ))}
          </List>
        </Stack>

        <Button variant="contained" onClick={() => setCreateDialogOpen(true)}>
          Create Expense Report
        </Button>
      </Stack>

      <CreateExpenseReportDialogBox
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
      />

      <Dialog open={aboutDialogOpen} onClose={() => setAboutDialogOpen(false)}>
        <DialogTitle>ExpenseIt Standalone</DialogTitle>
        <DialogContent>
          <Typography>ExpenseIt Standalone Sample Application, by the WPF SDK</Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAboutDialogOpen(false)}>OK</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

