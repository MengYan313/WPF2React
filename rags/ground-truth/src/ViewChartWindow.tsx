// 查看图表窗口组件 - 简化版
import { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Stack,
  Typography,
} from "@mui/material";
import { expenseData } from "./data";

interface ViewChartWindowProps {
  open: boolean;
  onClose: () => void;
}

/**
 * 查看图表窗口组件
 * 简化：当对话框打开时读取数据，移除观察者模式
 */
export function ViewChartWindow({ open, onClose }: ViewChartWindowProps) {
  // 每次渲染时直接从全局数据读取
  const lineItems = expenseData.lineItems.getItems();

  const maxCost = Math.max(...lineItems.map((item) => item.cost), 1);

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Expense Chart</DialogTitle>
      <DialogContent>
        <Stack spacing={2} mt={1}>
          {/* 简化图表显示 */}
          <Box
            display="flex"
            alignItems="flex-end"
            gap={1}
            minHeight={200}
            p={2}
            border={1}
            borderColor="divider"
          >
            {lineItems.map((item, index) => (
              <Stack key={index} flex={1} alignItems="center" gap={0.5}>
                <Box
                  width="100%"
                  height={`${(item.cost / maxCost) * 150}px`}
                  bgcolor="primary.main"
                  borderRadius={1}
                  display="flex"
                  alignItems="flex-end"
                  justifyContent="center"
                  color="white"
                  fontSize="0.75rem"
                  p={0.5}
                >
                  {item.cost}
                </Box>
                <Typography variant="caption" fontSize="0.7rem">
                  {item.description}
                </Typography>
              </Stack>
            ))}
          </Box>

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
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}

