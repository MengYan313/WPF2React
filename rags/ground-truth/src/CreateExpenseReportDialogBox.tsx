// 创建费用报告对话框组件 - 简化版
import { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  TextField,
  Box,
  Stack,
  Typography,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
} from "@mui/material";
import { expenseData } from "./data";
import { createLineItem } from "./LineItem";
import { ViewChartWindow } from "./ViewChartWindow";

interface CreateExpenseReportDialogBoxProps {
  open: boolean;
  onClose: () => void;
}

/**
 * 创建费用报告对话框组件
 * 简化：使用受控组件直接编辑，移除复杂的编辑模式切换
 */
export function CreateExpenseReportDialogBox({
  open,
  onClose,
}: CreateExpenseReportDialogBoxProps) {
  // 使用 key 属性在对话框打开时重置状态，移除 useEffect
  const [lineItems, setLineItems] = useState(() => expenseData.lineItems.getItems());
  const [viewChartOpen, setViewChartOpen] = useState(false);

  // 简化的事件处理函数
  const handleAddExpense = () => {
    // 创建空字符串的条目，使用 placeholder 显示提示
    const newItem = createLineItem("", "", 0);
    const updated = [...lineItems, newItem];
    setLineItems(updated);
    expenseData.lineItems.add(newItem);
  };

  const handleUpdateItem = (index: number, field: keyof typeof lineItems[0], value: string | number) => {
    const updated = [...lineItems];
    updated[index] = { ...updated[index], [field]: value };
    setLineItems(updated);
    expenseData.lineItems.update(index, updated[index]);
  };

  // 处理输入框聚焦：如果是默认提示文本，则清空
  const handleFocus = (index: number, field: "type" | "description") => {
    const item = lineItems[index];
    if (
      (field === "type" && item.type === "(Expense type)") ||
      (field === "description" && item.description === "(Description)")
    ) {
      handleUpdateItem(index, field, "");
    }
  };

  const handleOk = () => {
    const hasErrors = lineItems.some(
      (item) => !item.type || !item.description || item.cost <= 0
    );
    if (hasErrors) {
      alert("Please, fix the errors.");
      return;
    }
    alert("Expense Report Created!");
    onClose();
  };

  return (
    <>
      <Dialog 
        open={open} 
        onClose={onClose} 
        maxWidth="md" 
        fullWidth
        key={open ? "open" : "closed"}
      >
        <DialogTitle>Create Expense Report</DialogTitle>
        <DialogContent>
          <Stack spacing={2} mt={1}>
            {/* 简化报告详情显示 */}
            <TextField
              label="Email Alias"
              value={expenseData.alias}
              InputProps={{ readOnly: true }}
              size="small"
              fullWidth
            />
            <TextField
              label="Employee Number"
              value={expenseData.employeeNumber}
              InputProps={{ readOnly: true }}
              size="small"
              fullWidth
            />
            <TextField
              label="Cost Center"
              value={expenseData.costCenter}
              InputProps={{ readOnly: true }}
              size="small"
              fullWidth
            />

            <Box borderTop={1} borderColor="divider" pt={2} />

            {/* 简化表格编辑：直接使用受控输入框 */}
            <Stack direction="row" spacing={2}>
              <TableContainer component={Paper} sx={{ flex: 1 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Expense type</TableCell>
                      <TableCell>Description</TableCell>
                      <TableCell align="right">Cost</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {lineItems.map((item, index) => (
                      <TableRow key={index}>
                        <TableCell>
                          <TextField
                            value={item.type}
                            onChange={(e) => handleUpdateItem(index, "type", e.target.value)}
                            onFocus={() => handleFocus(index, "type")}
                            placeholder="(Expense type)"
                            size="small"
                            fullWidth
                          />
                        </TableCell>
                        <TableCell>
                          <TextField
                            value={item.description}
                            onChange={(e) => handleUpdateItem(index, "description", e.target.value)}
                            onFocus={() => handleFocus(index, "description")}
                            placeholder="(Description)"
                            size="small"
                            fullWidth
                          />
                        </TableCell>
                        <TableCell align="right">
                          <TextField
                            type="number"
                            value={item.cost || ""}
                            onChange={(e) => {
                              const value = parseInt(e.target.value, 10) || 0;
                              handleUpdateItem(index, "cost", value);
                            }}
                            size="small"
                            sx={{ width: 100 }}
                          />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>

              <Stack spacing={2}>
                <Button variant="outlined" onClick={handleAddExpense}>
                  Add Expense
                </Button>
                <Button variant="outlined" onClick={() => setViewChartOpen(true)}>
                  View Chart
                </Button>
              </Stack>
            </Stack>

            {/* 总费用 */}
            <Box borderTop={1} borderColor="divider" pt={2}>
              <Stack direction="row" justifyContent="space-between">
                <Typography fontWeight="bold">Total Expenses ($):</Typography>
                <Typography fontWeight="bold">{expenseData.totalExpenses}</Typography>
              </Stack>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose}>Cancel</Button>
          <Button onClick={handleOk} variant="contained">
            OK
          </Button>
        </DialogActions>
      </Dialog>

      <ViewChartWindow
        open={viewChartOpen}
        onClose={() => setViewChartOpen(false)}
      />
    </>
  );
}

